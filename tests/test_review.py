"""End-of-game review (PLAN D28) and the pattern detectors behind it (D29, D30).

Games are written straight into a SQLite session; the coach is fake. No engines, no API spend.
"""

import chess
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.game_service import Engines, GameError, GameService, Settings
from backend.review_service import ReviewService
from core.infrastructure.analysis.patterns import PlayerMove, development, tag_move
from core.infrastructure.coach.coach import CoachResult, GameSummary, Usage
from core.infrastructure.coach.traps import Trap
from core.infrastructure.postgresql.models import (
    Base,
    CoachExchange,
    Game,
    GameReview,
    LlmUsage,
    Move,
)


class FakeCoach:
    made: list = []  # noqa: RUF012 - shared on purpose, reset per test
    summaries = 0

    def __init__(self, model, after_game=False):
        self.model = model
        FakeCoach.made.append({"model": model, "after_game": after_game})

    def review(self, facts, reason, history=None, reveal=False):
        return CoachResult(
            reply=f"about {facts.move_san}",
            offer_retry=True,
            trap=Trap.NO_PLAN,
            proposed_trap_name=None,
            reply_model=self.model,
            usages=[
                Usage(self.model, "reply", {"input_tokens": 10, "output_tokens": 5}, 0.01),
                Usage("claude-haiku-5-5", "label", {"input_tokens": 10}, 0.001),
            ],
        )

    def explain_best(self, facts, history=None):
        return CoachResult(
            reply=f"best is {facts.best_move_san}",
            offer_retry=False,
            trap=Trap.NONE,
            proposed_trap_name=None,
            reply_model=self.model,
            usages=[Usage(self.model, "reveal", {"input_tokens": 5}, 0.002)],
        )

    def summarise(self, numbers):
        FakeCoach.summaries += 1
        return (
            GameSummary(went_well="w", patterns="p", keep_doing="k", work_on="o"),
            Usage(self.model, "summary", {"input_tokens": 50}, 0.02),
        )


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    FakeCoach.made, FakeCoach.summaries = [], 0
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def reviews(cap=5.0):
    games = GameService(Engines(None, None), Settings(spend_cap_usd=cap))
    return ReviewService(games, coach_factory=FakeCoach)


def facts_for(board, uci, **extra):
    move = chess.Move.from_uci(uci)
    base = {
        "fen_before": board.fen(),
        "player_color": "white" if board.turn else "black",
        "move_san": board.san(move),
        "quality": extra.pop("quality", "good"),
        "win_prob_before": 0.5,
        "win_prob_after": 0.5,
        "best_move_san": None,
        "best_line_san": [],
        "threats_they_had": [],
        "pieces_left_hanging": [],
        "free_captures_missed": [],
    }
    return base | extra


def make_game(session, plies, status="finished", exclude=False):
    """plies: list of uci, or (uci, {quality, wpb, wpa, facts, think_ms, caught}) for player
    (white) moves. `caught` = warned and taken back: stored, but the board doesn't advance."""
    game = Game(
        player_color="white",
        bot_elo=400,
        bot_temperature=1.0,
        status=status,
        result="0-1" if status == "finished" else None,
        end_reason="checkmate" if status == "finished" else None,
        exclude_from_profile=exclude,
    )
    session.add(game)
    board = chess.Board()
    for ply in plies:
        uci, info = ply if isinstance(ply, tuple) else (ply, {})
        move = chess.Move.from_uci(uci)
        caught = info.get("caught", False)
        if board.turn == chess.WHITE:  # player
            quality = info.get("quality", "good")
            wpb, wpa = info.get("wpb", 0.5), info.get("wpa", 0.5)
            facts = facts_for(
                board,
                uci,
                quality=quality,
                win_prob_before=wpb,
                win_prob_after=wpa,
                **info.get("facts", {}),
            )
            session.add(
                Move(
                    game=game,
                    by="player",
                    uci=uci,
                    san=board.san(move),
                    fen_before=board.fen(),
                    quality=quality,
                    win_prob_before=wpb,
                    win_prob_after=wpa,
                    facts=facts,
                    think_ms=info.get("think_ms"),
                    taken_back=caught,
                    warning="⚠ This loses about 3 points of material." if caught else None,
                    warning_outcome="took_back" if caught else None,
                    eval_cp_after=-300 if caught else 0,
                )
            )
            if caught:
                continue
        else:
            session.add(
                Move(game=game, by="bot", uci=uci, san=board.san(move), fen_before=board.fen())
            )
        board.push(move)
    session.commit()
    return game


# A game with four bad player moves of different cost: a3 (-0.20), h3 (-0.40), b3 (-0.10),
# g3 (-0.30). The three costliest are h3, g3, a3, shown in game order: a3, h3, g3.
FOUR_MISTAKES = [
    ("a2a3", {"quality": "blunder", "wpb": 0.5, "wpa": 0.3}),
    "e7e5",
    ("h2h3", {"quality": "blunder", "wpb": 0.6, "wpa": 0.2, "facts": {"best_move_san": "e4"}}),
    "d7d5",
    ("b2b3", {"quality": "mistake", "wpb": 0.5, "wpa": 0.4}),
    "g8f6",
    ("g2g3", {"quality": "blunder", "wpb": 0.5, "wpa": 0.2}),
]


def test_review_needs_a_finished_game(session):
    game = make_game(session, ["e2e4"], status="player_turn")
    with pytest.raises(GameError, match="finished"):
        reviews().review(session, game)


def test_three_costliest_mistakes_in_game_order(session):
    game = make_game(session, FOUR_MISTAKES)
    cards = reviews().review(session, game)["mistakes"]
    assert [c["san"] for c in cards] == ["a3", "h3", "g3"]
    assert cards[0]["question"] == "Why did you play a3?"


def test_refutation_and_better_move_hidden_until_answered_or_skipped(session):
    game = make_game(session, FOUR_MISTAKES)
    svc = reviews()
    h3 = svc.review(session, game)["mistakes"][1]
    assert h3["best_move_san"] is None and h3["their_line_uci"] == ["h2h3"]
    svc.skip(session, game, h3["move_id"])
    h3 = svc.review(session, game)["mistakes"][1]
    assert h3["skipped"] and h3["best_move_san"] == "e4" and h3["best_uci"] == "e2e4"


def test_answer_gets_an_after_game_reply_label_and_usage(session):
    game = make_game(session, FOUR_MISTAKES)
    svc = reviews()
    move_id = svc.review(session, game)["mistakes"][0]["move_id"]
    svc.answer(session, game, move_id, "no idea", "claude-sonnet-5-5")
    card = svc.review(session, game)["mistakes"][0]
    assert card["reply"] == "about a3" and card["player_reason"] == "no idea"
    assert FakeCoach.made[-1]["after_game"] is True
    ex = session.scalar(select(CoachExchange))
    assert ex.reason_asked == "review" and ex.trap == "no_plan"
    assert sorted(session.scalars(select(LlmUsage.purpose))) == ["label", "reply"]
    # The reason given now counts in the review's patterns.
    assert svc.numbers(session, game)["traps"]["this_game"] == {"no_plan": 1}


def test_only_the_shown_mistakes_can_be_answered(session):
    game = make_game(session, FOUR_MISTAKES)
    b3 = next(m for m in game.moves if m.san == "b3")
    with pytest.raises(GameError, match="reviewed mistakes"):
        reviews().answer(session, game, b3.id, "x", "claude-sonnet-5-5")


def test_reveal_after_answering(session):
    game = make_game(session, FOUR_MISTAKES)
    svc = reviews()
    h3 = svc.review(session, game)["mistakes"][1]["move_id"]
    with pytest.raises(GameError, match="first"):
        svc.reveal(session, game, h3, "claude-sonnet-5-5")
    svc.skip(session, game, h3)
    svc.reveal(session, game, h3, "claude-sonnet-5-5")
    assert svc.review(session, game)["mistakes"][1]["reveal_reply"] == "best is e4"


def test_summary_written_once_then_cached(session):
    game = make_game(session, FOUR_MISTAKES)
    svc = reviews()
    svc.summarise(session, game, "claude-sonnet-5-5")
    svc.summarise(session, game, "claude-sonnet-5-5")
    assert FakeCoach.summaries == 1
    assert svc.review(session, game)["summary"]["work_on"] == "o"
    stored = session.scalar(select(GameReview))
    assert stored.numbers["moves_played"] == 4  # what it was written from is kept (risk R3)
    assert session.scalar(select(LlmUsage.purpose)) == "summary"


def test_spend_cap_pauses_answers_and_summary(session):
    game = make_game(session, FOUR_MISTAKES)
    svc = reviews(cap=0.0)
    move_id = svc.review(session, game)["mistakes"][0]["move_id"]
    svc.answer(session, game, move_id, "no idea", "claude-sonnet-5-5")
    assert "paused" in svc.review(session, game)["mistakes"][0]["reply"]
    with pytest.raises(GameError, match="paused"):
        svc.summarise(session, game, "claude-sonnet-5-5")
    assert FakeCoach.made == []
    assert session.scalar(select(func.count(LlmUsage.id))) == 0


def test_history_skips_excluded_unfinished_and_later_games(session):
    make_game(session, ["e2e4"])  # counts
    make_game(session, ["e2e4"], exclude=True)  # game 50-style test game: never counts
    make_game(session, ["e2e4"], status="player_turn")  # abandoned
    game = make_game(session, FOUR_MISTAKES)
    make_game(session, ["e2e4"])  # later game
    assert reviews().numbers(session, game)["history_games"] == 1


def test_think_time_medians_split_by_quality(session):
    plies = []
    good = ["e2e4", "d2d4", "g1f3"]
    for i, uci in enumerate(good):
        plies += [(uci, {"think_ms": 2000 + i}), ["e7e6", "d7d6", "g8f6"][i]]
    plies += [("b1c3", {"quality": "blunder", "think_ms": 9000}), "c7c6"]
    plies += [("f1d3", {"quality": "blunder", "think_ms": 11000}), "b7b6"]
    plies += [("c1e3", {"quality": "mistake", "think_ms": 10000})]
    game = make_game(session, plies)
    medians = reviews().numbers(session, game)["think_seconds"]["this_game"]
    assert medians == {"ok_moves": 2.0, "bad_moves": 10.0}


# --- detectors (D29) ---------------------------------------------------------------------


def pm(board, uci, quality="good", wpb=0.5, **facts):
    return PlayerMove(
        1, 1, board.san(chess.Move.from_uci(uci)), uci, board.fen(), quality, wpb, wpb, facts
    )


def test_ignored_threat_when_their_reply_takes_the_threatened_piece():
    # Black knight on e5 is attacked by the f3 knight and undefended; black plays a6 instead.
    board = chess.Board("rnbqkb1r/pppp1ppp/8/4n3/8/5N2/PPPP1PPP/RNBQKB1R b KQkq - 0 4")
    tags = tag_move(pm(board, "a7a6", "blunder", their_best_reply_san="Nxe5")).tags
    assert tags["threats"] is False
    assert tags["safety"] is True  # the piece was already threatened: not a new exposure


def test_dealing_with_a_threat_is_a_highlight():
    board = chess.Board("rnbqkb1r/pppp1ppp/8/4n3/8/5N2/PPPP1PPP/RNBQKB1R b KQkq - 0 4")
    result = tag_move(pm(board, "e5c6"))
    assert result.tags["threats"] is True
    assert result.moment.text == "Dealt with the threat to your knight on e5"


def test_moving_a_piece_into_capture_is_a_safety_miss():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("d6")  # opens the c8 bishop's diagonal to g4
    tags = tag_move(pm(board, "d1g4", "blunder", their_best_reply_san="d5")).tags
    assert tags["safety"] is True  # their best reply isn't a capture: not blamed on safety
    tags = tag_move(pm(board, "d1g4", "blunder", their_best_reply_san="Bxg4")).tags
    assert tags["safety"] is False


def test_taking_a_free_piece_is_a_highlight():
    board = chess.Board("rnbqkb1r/pppp1ppp/8/4n3/8/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4")
    result = tag_move(pm(board, "f3e5"))
    assert result.tags["captures"] is True
    assert result.moment.text == "Took the free knight on e5"


def test_development_needs_castling_and_three_minor_pieces():
    sans = ["e4", "Nf3", "Bc4", "Nc3", "O-O", "d3", "h3", "a3", "Re1", "Be3"]
    replies = ["a7a6", "h7h6", "a6a5", "h6h5", "a8a7", "h8h7", "a7a6", "h7h6", "a6a8", "h6h8"]
    board, moves = chess.Board(), []
    for san, reply in zip(sans, replies, strict=True):
        move = board.parse_san(san)
        moves.append(PlayerMove(1, 1, san, move.uci(), board.fen(), "good", 0.5, 0.5, {}))
        board.push(move)
        board.push_uci(reply)
    assert development(moves) is True
    assert development(moves[:9]) is None  # too short to judge


# --- blunders the warning caught (user feedback, 6 Nov 2026) ------------------------------
# A blunder taken back after the D27 warning was still the player's decision; leaving it out
# made "no blunders" hollow.

CAUGHT_ONLY = [
    ("e2e4", {}),
    "e7e5",
    ("d1h5", {"quality": "blunder", "wpb": 0.5, "wpa": 0.1, "caught": True, "think_ms": 9000}),
    ("g1f3", {}),
    "b8c6",
]


def test_caught_blunder_is_one_of_the_costliest_moves(session):
    game = make_game(session, CAUGHT_ONLY)
    review = reviews().review(session, game)
    cards = review["mistakes"]
    assert [c["san"] for c in cards] == ["Qh5"]
    assert cards[0]["caught_by_warning"] is True
    assert review["numbers"]["warnings"]["this_game"] == {"shown": 1, "taken_back": 1, "kept": 0}
    assert review["numbers"]["mistakes"][0]["taken_back_after_warning"] is True


def test_caught_blunder_counts_in_patterns_and_timing(session):
    game = make_game(session, CAUGHT_ONLY)
    numbers = reviews().numbers(session, game)
    safety = next(p for p in numbers["patterns"] if p["key"] == "safety")
    assert safety["this_game"]["opportunities"] == 3  # e4, the caught Qh5, Nf3
    assert numbers["moves_played"] == 3


def test_caught_blunder_can_be_answered(session):
    game = make_game(session, CAUGHT_ONLY)
    svc = reviews()
    move_id = svc.review(session, game)["mistakes"][0]["move_id"]
    svc.answer(session, game, move_id, "attacking f7", "claude-sonnet-5-5")
    assert svc.review(session, game)["mistakes"][0]["reply"] == "about Qh5"


def test_usual_caught_per_game_only_counts_games_that_had_warnings(session):
    old = make_game(session, ["e2e4"])  # before warnings existed: no eval_cp_after
    for m in old.moves:
        m.eval_cp_after = None
    session.commit()
    make_game(session, CAUGHT_ONLY)  # 1 caught
    make_game(session, [("e2e4", {})])  # 0 caught
    game = make_game(session, [("d2d4", {})])
    warnings = reviews().numbers(session, game)["warnings"]
    assert warnings["usual_taken_back_per_game"] == 0.5


def test_development_ignores_taken_back_moves():
    sans = ["e4", "Nf3", "Bc4", "Nc3", "O-O", "d3", "h3", "a3", "Re1", "Be3"]
    replies = ["a7a6", "h7h6", "a6a5", "h6h5", "a8a7", "h8h7", "a7a6", "h7h6", "a6a8", "h6h8"]
    board, moves = chess.Board(), []
    for san, reply in zip(sans, replies, strict=True):
        if san == "Nf3":  # a caught blunder first, taken back
            moves.append(
                PlayerMove(
                    1, 1, "Qh5", "d1h5", board.fen(), "blunder", 0.5, 0.1, {}, taken_back=True
                )
            )
        move = board.parse_san(san)
        moves.append(PlayerMove(1, 1, san, move.uci(), board.fen(), "good", 0.5, 0.5, {}))
        board.push(move)
        board.push_uci(reply)
    assert development(moves) is True


def test_warned_taken_back_then_replayed_is_one_card(session):
    # Game 48: warned about O-O, took it back, played O-O again and kept it.
    replay = ("d1h5", {"quality": "blunder", "wpb": 0.5, "wpa": 0.1})
    game = make_game(
        session,
        [
            ("e2e4", {}),
            "e7e5",
            ("d1h5", {"quality": "blunder", "wpb": 0.5, "wpa": 0.1, "caught": True}),
            replay,
            "b8c6",
        ],
    )
    cards = reviews().review(session, game)["mistakes"]
    assert len(cards) == 1
    assert cards[0]["caught_by_warning"] is False and cards[0]["played_anyway"] is True
