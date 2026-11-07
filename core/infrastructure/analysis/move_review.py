"""Build the engine-fact bundle for one move: the only chess truth the coach gets (PLAN D1)."""

from __future__ import annotations

from dataclasses import dataclass, field

import chess

from core.infrastructure.analysis.classify import classify
from core.infrastructure.analysis.facts import (
    VALUE,
    free_captures,
    hanging_pieces,
    threats_of_last_move,
)
from core.infrastructure.engines.stockfish import Evaluation, Judge


@dataclass
class MoveFacts:
    fen_before: str
    player_color: str  # "white" | "black"
    move_san: str
    quality: str  # good / inaccuracy / mistake / blunder
    win_prob_before: float  # for the player who moved
    win_prob_after: float
    best_move_san: str | None
    best_line_san: list[str]
    threats_they_had: list[str]  # what the opponent's last move threatened
    pieces_left_hanging: list[str]  # player's pieces hanging after the move
    # Captures the player could have made instead, each with Stockfish's rating of it.
    # Only captures rated good/inaccuracy are listed: a capture the engine calls a mistake
    # isn't free, however it looks (game 7: Qxg4 was called free and also criticised).
    free_captures_missed: list[dict]
    # D20: how the opponent punishes the move, so the coach can explain *why* it was bad.
    their_best_reply_san: str | None = None
    their_best_line_san: list[str] = field(default_factory=list)
    # D20: piece list, so the coach never has to parse a FEN to know where things are.
    pieces: dict[str, list[str]] = field(default_factory=dict)


def piece_list(board: chess.Board) -> dict[str, list[str]]:
    out = {}
    for color, name in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        items = sorted(
            (
                (
                    VALUE[p.piece_type] if p.piece_type != chess.KING else 100,
                    chess.square_name(sq),
                    chess.piece_name(p.piece_type),
                )
                for sq, p in board.piece_map().items()
                if p.color == color
            ),
            reverse=True,
        )
        out[name] = [f"{piece} {square}" for _, square, piece in items]
    return out


@dataclass
class MoveAnalysis:
    """Facts for the coach plus the raw evaluations (pov = mover), which stay out of the coach's
    prompt but drive the blunder warning (D27)."""

    facts: MoveFacts
    before: Evaluation
    after: Evaluation


def review_move(
    judge: Judge, board: chess.Board, move: chess.Move, before: Evaluation | None = None
) -> tuple[MoveFacts, Evaluation]:
    """`board` is the position before `move`; it is not modified.

    `before` may be passed in when the caller already evaluated this position (saves a search).
    Returns the facts and the evaluation of the position after the move (pov = mover), which the
    caller can reuse as the next `before` for the opponent with `1 - win_prob`.
    """
    analysis = analyse_move(judge, board, move, before)
    return analysis.facts, analysis.after


def analyse_move(
    judge: Judge, board: chess.Board, move: chess.Move, before: Evaluation | None = None
) -> MoveAnalysis:
    """review_move, also returning the evaluation before the move."""
    mover = board.turn
    if before is None or before.pov != mover:
        before = judge.evaluate(board, mover)
    best_line = board.variation_san(before.pv[:4]).split() if before.pv else []
    threats = threats_of_last_move(board)
    available = free_captures(board)
    san = board.san(move)

    after_board = board.copy()
    after_board.push(move)
    after = judge.evaluate(after_board, mover)
    quality, _ = classify(before.win_prob, after.win_prob)
    missed = _rated_captures(judge, board, [c for c in available if c != san], before.win_prob)
    reply_line = after_board.variation_san(after.pv[:4]).split() if after.pv else []
    return MoveAnalysis(
        MoveFacts(
            fen_before=board.fen(),
            player_color="white" if mover == chess.WHITE else "black",
            move_san=san,
            quality=quality.value,
            win_prob_before=round(before.win_prob, 3),
            win_prob_after=round(after.win_prob, 3),
            best_move_san=board.san(before.best_move) if before.best_move else None,
            best_line_san=_strip_numbers(best_line),
            threats_they_had=threats,
            pieces_left_hanging=hanging_pieces(after_board, mover),
            free_captures_missed=missed,
            their_best_reply_san=after_board.san(after.best_move) if after.best_move else None,
            their_best_line_san=_strip_numbers(reply_line),
            pieces=piece_list(board),
        ),
        before,
        after,
    )


def _rated_captures(
    judge: Judge, board: chess.Board, sans: list[str], best_win_prob: float
) -> list[dict]:
    """Rate each candidate capture with the engine; keep the ones that really hold up."""
    out = []
    for san in sans:
        trial = board.copy()
        trial.push_san(san)
        rating, _ = classify(best_win_prob, judge.evaluate(trial, board.turn).win_prob)
        if rating.value in ("good", "inaccuracy"):
            out.append({"move": san, "engine_rating": rating.value})
    return out


def _strip_numbers(tokens: list[str]) -> list[str]:
    """variation_san gives '4.', '4...' tokens; keep only moves."""
    return [t for t in tokens if not t[0].isdigit()]
