"""Playstyle profile (PLAN D31) and only-move detection (X11). Fake data, no engines, no spend."""

import chess

from backend.profile_service import ProfileService, eval_state, phase
from core.infrastructure.analysis.patterns import tag_move
from tests.test_review import FOUR_MISTAKES, make_game, pm, session  # noqa: F401 - fixture

# --- only move (X11) -----------------------------------------------------------------------


def test_only_move_found_when_second_best_was_far_worse():
    board = chess.Board()
    result = tag_move(pm(board, "e2e4", "good", wpb=0.6, second_best_win_prob=0.4))
    assert result.tags["only_move"] is True
    assert result.moment.text == "Found the only move that held the position"


def test_only_move_missed_when_played_move_was_worse():
    board = chess.Board()
    tags = tag_move(pm(board, "a2a3", "mistake", wpb=0.6, second_best_win_prob=0.4)).tags
    assert tags["only_move"] is False


def test_no_only_move_opportunity_when_alternatives_were_fine_or_unknown():
    board = chess.Board()
    assert "only_move" not in tag_move(pm(board, "e2e4", wpb=0.6, second_best_win_prob=0.58)).tags
    assert "only_move" not in tag_move(pm(board, "e2e4", wpb=0.6)).tags  # stored before X11


# --- phase / eval state ------------------------------------------------------------------


def test_phase_opening_middlegame_endgame():
    assert phase(chess.STARTING_FEN) == "opening"
    # Move 20, queens on, full armies: middlegame.
    assert phase("r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 20") == (
        "middlegame"
    )
    # Queens off after move 10: endgame.
    assert phase("r1b1kb1r/pppp1ppp/2n2n2/4p3/4P3/2N2N2/PPPP1PPP/R1B1KB1R w KQkq - 0 20") == (
        "endgame"
    )
    # Queens on, but each side has only a queen and a knight (12 points): endgame.
    assert phase("3qk3/8/2n5/8/8/2N5/8/3QK3 w - - 0 40") == "endgame"


def test_eval_state_bands():
    assert eval_state(0.7) == "ahead"
    assert eval_state(0.5) == "level"
    assert eval_state(0.3) == "behind"


# --- profile -----------------------------------------------------------------------------


def test_profile_skips_excluded_games_but_lists_them(session):  # noqa: F811
    make_game(session, FOUR_MISTAKES)
    make_game(session, FOUR_MISTAKES, exclude=True)
    p = ProfileService().profile(session)
    assert p["games_counted"] == 1
    assert p["games_excluded"] == 1
    assert [g["excluded"] for g in p["games"]] == [True, False]  # newest first
    opening = p["breakdowns"]["phase"]["opening"]
    assert (opening["moves"], opening["bad_moves"]) == (4, 4)


def test_trend_needs_enough_chances_in_both_windows(session):  # noqa: F811
    for _ in range(3):
        make_game(session, ["e2e4", "e7e5"])
    safety = next(p for p in ProfileService().profile(session)["patterns"] if p["key"] == "safety")
    assert safety["recent"]["opportunities"] == 3
    assert safety["trend"] is None


def test_trend_compares_last_ten_games_with_the_ten_before(session):  # noqa: F811
    # 10 older games: a3 is punished by Bxa3 (a safety miss); e4 and h3 aren't. 2/3 each.
    # 10 recent games: three good moves. Safety goes from 2/3 to 3/3.
    bad = {"quality": "blunder", "facts": {"their_best_reply_san": "Bxa3"}}
    older = ["e2e4", "e7e6", ("a2a3", bad), "d7d6", ("h2h3", {"quality": "blunder"})]
    for _ in range(10):
        make_game(session, older)
    for _ in range(10):
        make_game(session, ["e2e4", "e7e6", "d2d4", "d7d6", "g1f3"])
    safety = next(p for p in ProfileService().profile(session)["patterns"] if p["key"] == "safety")
    assert safety["recent"]["rate"] == 1.0
    assert (safety["previous"]["hits"], safety["previous"]["opportunities"]) == (20, 30)
    assert safety["trend"] == 0.333


def test_think_time_split_shown_only_from_twenty_moves(session):  # noqa: F811
    plies = []
    for uci, reply in [("e2e4", "e7e5"), ("g1f3", "b8c6")]:
        plies += [(uci, {"think_ms": 4000}), reply]
    make_game(session, plies)
    timing = ProfileService().profile(session)["timing"]
    assert timing["ok_vs_bad"]["ok"] == {"moves": 2, "median_s": None}
    for _ in range(10):
        make_game(session, plies)
    timing = ProfileService().profile(session)["timing"]
    assert timing["ok_vs_bad"]["ok"] == {"moves": 22, "median_s": 4.0}
