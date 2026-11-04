"""P0-2: hand-checked positions. Each expectation was worked out by hand, not by running the code."""

import os
import shutil

import chess
import pytest

from core.infrastructure.analysis.classify import Quality, classify
from core.infrastructure.analysis.facts import free_captures, hanging_pieces, threats_of_last_move


def board_after(*sans: str, fen: str | None = None) -> chess.Board:
    board = chess.Board(fen) if fen else chess.Board()
    for san in sans:
        board.push_san(san)
    return board


# --- hanging pieces ---------------------------------------------------------------


def test_undefended_pawn_is_hanging_defended_one_is_not():
    # 1.e4 d5: e4 is attacked by d5 and undefended; d5 is attacked by e4 but the d8 queen
    # defends it down the now-open d-file, and pawn-for-pawn is not a loss.
    board = board_after("e4", "d5")
    assert hanging_pieces(board, chess.WHITE) == ["pawn on e4"]
    assert hanging_pieces(board, chess.BLACK) == []


def test_piece_attacked_by_cheaper_piece_is_hanging():
    # Knight e5 attacked by pawn d6: losing a 3 for a 1 even if it were defended.
    board = chess.Board("4k3/8/3p4/4N3/8/8/8/4K3 w - - 0 1")
    assert hanging_pieces(board, chess.WHITE) == ["knight on e5"]
    assert hanging_pieces(board, chess.BLACK) == []


def test_defended_piece_attacked_by_equal_piece_is_not_hanging():
    # Queens face off on the d-file; white's is defended by the king, black's is not.
    board = chess.Board("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1")
    assert hanging_pieces(board, chess.WHITE) == []
    assert hanging_pieces(board, chess.BLACK) == ["queen on d5"]


def test_start_position_has_nothing_hanging():
    board = chess.Board()
    assert hanging_pieces(board, chess.WHITE) == []
    assert hanging_pieces(board, chess.BLACK) == []


# --- free captures ----------------------------------------------------------------


def test_free_capture_of_undefended_queen():
    board = chess.Board("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1")
    assert free_captures(board) == ["Qxd5"]


def test_equal_trade_is_not_a_free_capture():
    # exd5 is available but d5 is defended by the queen: a trade, not a gift.
    assert free_captures(board_after("e4", "d5")) == []


# --- threats of the last move -----------------------------------------------------


def test_scholars_setup_bishop_eyes_f7():
    board = board_after("e4", "e5", "Qh5", "Nc6", "Bc4")
    assert threats_of_last_move(board) == ["bishop attacks pawn on f7"]


def test_mating_move_reports_check_and_attacks():
    # 1.e4 f6 2.d4 g5 3.Qh5#: check along h5-e8, plus the queen hits g5 and h7.
    board = board_after("e4", "f6", "d4", "g5", "Qh5")
    threats = threats_of_last_move(board)
    assert threats[0] == "check"
    assert set(threats[1:]) == {"queen attacks pawn on g5", "queen attacks pawn on h7"}


def test_no_moves_no_threats():
    assert threats_of_last_move(chess.Board()) == []


# --- classification ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (0.50, 0.50, Quality.GOOD),
        (0.50, 0.46, Quality.GOOD),
        (0.50, 0.44, Quality.INACCURACY),
        (0.50, 0.39, Quality.MISTAKE),
        (0.50, 0.20, Quality.BLUNDER),
        (0.40, 0.55, Quality.GOOD),  # position improved
    ],
)
def test_classify(before, after, expected):
    assert classify(before, after)[0] is expected


# --- Stockfish judge (needs the binary: runs in the api container) ------------------

stockfish = pytest.mark.skipif(
    not shutil.which(os.environ.get("STOCKFISH_PATH", "stockfish")), reason="no stockfish"
)


@stockfish
def test_judge_finds_mate_in_one():
    from core.infrastructure.engines.stockfish import Judge

    board = board_after("e4", "f6", "d4", "g5")
    with Judge(depth=10) as judge:
        ev = judge.evaluate(board, chess.WHITE)
    assert board.san(ev.best_move) == "Qh5#"
    assert ev.mate_in == 1
    assert ev.win_prob > 0.99


@stockfish
def test_judge_is_deterministic():
    """Same position, same verdict, whatever was analysed before (game 7 finding)."""
    from core.infrastructure.engines.stockfish import Judge

    target = board_after("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6")
    with Judge(depth=12) as judge:
        first = judge.evaluate(target, chess.WHITE).win_prob
        judge.evaluate(board_after("d4", "d5", "c4"), chess.BLACK)  # pollute the hash
        assert judge.evaluate(target, chess.WHITE).win_prob == first


@stockfish
def test_judge_sees_hung_queen():
    from core.infrastructure.engines.stockfish import Judge

    # Black to move can take an undefended queen (white king on h1, not e1): hugely winning.
    board = chess.Board("4k3/8/8/3q4/8/8/8/3Q3K b - - 0 1")
    with Judge(depth=10) as judge:
        ev = judge.evaluate(board, chess.BLACK)
    assert board.san(ev.best_move) == "Qxd1+"
    assert ev.win_prob > 0.95


def test_poisoned_capture_is_not_called_free():
    """A capture the engine rates as a mistake must not be listed as free (game 7, Qxg4)."""
    from core.infrastructure.analysis.move_review import _rated_captures
    from core.infrastructure.engines.stockfish import Evaluation

    class LosingJudge:
        def evaluate(self, board, pov):
            return Evaluation(pov, 0.2, 0, None, None, [])  # the capture loses

    class FineJudge:
        def evaluate(self, board, pov):
            return Evaluation(pov, 0.5, 0, None, None, [])

    board = chess.Board("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1")
    assert _rated_captures(LosingJudge(), board, ["Qxd5"], best_win_prob=0.5) == []
    assert _rated_captures(FineJudge(), board, ["Qxd5"], 0.5) == [
        {"move": "Qxd5", "engine_rating": "good"}
    ]
