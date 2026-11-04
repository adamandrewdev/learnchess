"""Game flow with fake engines and a fake coach: no Stockfish, no Maia, no API spend."""

import random
from typing import ClassVar

import chess
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.game_service import Engines, GameError, GameService, Settings
from core.infrastructure.coach.coach import CoachResult, Usage
from core.infrastructure.coach.traps import Trap
from core.infrastructure.engines.stockfish import Evaluation
from core.infrastructure.postgresql.models import Base, CoachExchange, LlmUsage


class FakeJudge:
    """White's win prob is `base`. A move listed in `after` sets the mover's win prob to that."""

    def __init__(self, blunders=(), after=None, base=0.5):
        self.after = {m: 0.1 for m in blunders} | (after or {})
        self.base = base

    def evaluate(self, board, pov):
        wp_white = self.base
        if board.move_stack and board.peek().uci() in self.after:
            mover_wp = self.after[board.peek().uci()]
            mover = not board.turn
            wp_white = mover_wp if mover == chess.WHITE else 1 - mover_wp
        wp = wp_white if pov == chess.WHITE else 1 - wp_white
        best = next(iter(board.legal_moves), None)
        return Evaluation(pov, wp, 0, None, best, [best] if best else [])


class FakeOpponent:
    seed = 0

    def set_strength(self, elo, temperature=1.0):
        pass

    def play(self, board):
        return min(board.legal_moves, key=lambda m: m.uci())


class FakeCoach:
    calls = 0
    last: ClassVar[dict] = {}  # what the last call received, for assertions

    def __init__(self, model):
        self.model = model

    def review(self, facts, reason, history=None, reveal=False):
        FakeCoach.calls += 1
        FakeCoach.last = {"kind": "review", "history": history, "reveal": reveal}
        return CoachResult(
            reply=f"about {facts.move_san}",
            offer_retry=facts.quality != "good",
            trap=Trap.IGNORED_THREAT,
            proposed_trap_name=None,
            reply_model=self.model,
            usages=[
                Usage(self.model, "reply", {"input_tokens": 100, "output_tokens": 10}, 0.01),
                Usage(
                    "claude-haiku-5-5", "label", {"input_tokens": 100, "output_tokens": 5}, 0.001
                ),
            ],
        )

    def explain_best(self, facts, history=None):
        FakeCoach.last = {"kind": "explain", "history": history}
        return CoachResult(
            reply=f"best is {facts.best_move_san}",
            offer_retry=True,
            trap=Trap.NONE,
            proposed_trap_name=None,
            reply_model=self.model,
            usages=[Usage(self.model, "reveal", {"input_tokens": 50, "output_tokens": 5}, 0.002)],
        )


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def service(blunders=(), check_rate=0.0, cap=5.0, after=None, base=0.5):
    return GameService(
        Engines(FakeJudge(blunders, after, base), FakeOpponent()),
        Settings(
            bot_elo=400,
            bot_temperature=1.0,
            good_move_check_rate=check_rate,
            coach_min_quality="mistake",
            spend_cap_usd=cap,
            still_winning=0.85,
            reveal_after_retries=2,
        ),
        coach_factory=FakeCoach,
        rng=random.Random(0),
    )


def test_good_move_no_coach_bot_replies(session):
    svc = service()
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4")
    state = svc.state(session, game)
    assert state["status"] == "player_turn"
    assert len(state["moves"]) == 2  # player + bot
    assert state["last_move"]["by"] == "bot"


def test_blunder_asks_why_and_bot_waits(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    state = svc.state(session, game)
    assert state["status"] == "awaiting_reason"
    assert state["moves"] == ["f3"]  # bot has not moved
    assert state["coach_log"][-1]["question"] == "Why did you play f3?"
    assert state["coach_log"][-1]["quality"] is None  # not revealed before the reply


def test_reason_reply_retry_takes_move_back(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.submit_reason(session, game, "attacking", "claude-sonnet-5-5")
    state = svc.state(session, game)
    assert state["status"] == "coach_replied"
    assert state["coach_log"][-1]["reply"] == "about f3"
    assert state["coach_log"][-1]["quality"] == "blunder"
    assert state["spend"]["month_usd"] == pytest.approx(0.011)

    svc.continue_game(session, game, retry=True)
    state = svc.state(session, game)
    assert state["status"] == "player_turn"
    assert state["moves"] == []
    assert state["fen"] == chess.STARTING_FEN
    assert session.scalar(select(CoachExchange.outcome)) == "retried"
    # The advice stays visible after the takeback (M1 browser check found it vanishing).
    assert state["coach_log"][-1]["reply"] == "about f3"
    assert state["coach_log"][-1]["taken_back"] is True
    assert session.scalar(select(CoachExchange.trap)) == "ignored_threat"  # stored (D12)


def test_continue_lets_bot_move(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.submit_reason(session, game, "no idea", "gpt-5.1")
    svc.continue_game(session, game, retry=False)
    state = svc.state(session, game)
    assert state["status"] == "player_turn"
    assert len(state["moves"]) == 2


def test_usage_rows_recorded_per_call(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.submit_reason(session, game, "x", "claude-sonnet-5-5")
    rows = session.scalars(select(LlmUsage)).all()
    assert sorted(r.purpose for r in rows) == ["label", "reply"]
    assert all(r.exchange_id is not None for r in rows)


def test_spend_cap_blocks_the_call_with_visible_message(session):
    FakeCoach.calls = 0
    svc = service(blunders={"f2f3"}, cap=0.0)
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.submit_reason(session, game, "x", "claude-sonnet-5-5")
    state = svc.state(session, game)
    assert FakeCoach.calls == 0
    assert "budget is used up" in state["coach_log"][-1]["reply"]
    assert state["coach_log"][-1]["offer_retry"] is True
    assert session.scalar(select(func.count(LlmUsage.id))) == 0


def test_good_move_check_sampling(session):
    svc = service(check_rate=1.0)  # always check
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4")
    assert svc.state(session, game)["status"] == "awaiting_reason"


def test_playing_black_bot_moves_first(session):
    svc = service()
    game = svc.new_game(session, "black")
    state = svc.state(session, game)
    assert len(state["moves"]) == 1 and state["last_move"]["by"] == "bot"


@pytest.mark.parametrize(
    "uci,match", [("e2e5", "illegal"), ("zz", "bad move"), ("e7e5", "illegal")]
)
def test_rejects_bad_moves(session, uci, match):
    svc = service()
    game = svc.new_game(session, "white")
    with pytest.raises(GameError, match=match):
        svc.player_move(session, game, uci)


def test_cannot_move_while_question_pending(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    with pytest.raises(GameError, match="not your turn"):
        svc.player_move(session, game, "e2e4")


def test_empty_reason_rejected(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    with pytest.raises(GameError, match="tell the coach"):
        svc.submit_reason(session, game, "   ", "claude-sonnet-5-5")


def test_checkmate_finishes_game(session):
    # Fool's mate with the player as black: 1.f3 e5 2.g4 Qh4#. Fake bot plays the first
    # legal move alphabetically, so drive white's moves via the opponent.
    svc = service()
    script = iter(["f2f3", "g2g4"])
    svc.engines.opponent.play = lambda board: chess.Move.from_uci(next(script))
    game = svc.new_game(session, "black")
    svc.player_move(session, game, "e7e5")
    svc.player_move(session, game, "d8h4")
    state = svc.state(session, game)
    assert state["status"] == "finished"
    assert state["result"] == "0-1"
    assert state["end_reason"] == "checkmate"


# --- game 7 fixes ---------------------------------------------------------------------


def test_inaccuracy_does_not_stop_the_player(session):
    svc = service(after={"g2g4": 0.43})  # 0.50 -> 0.43: an inaccuracy
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "g2g4")
    assert svc.state(session, game)["status"] == "player_turn"


def test_no_stop_while_still_clearly_winning(session):
    # Game 7's Qxg4: 0.98 -> 0.88 is a "mistake" by the numbers, but you're still winning.
    svc = service(base=0.98, after={"g2g4": 0.88})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "g2g4")
    assert svc.state(session, game)["status"] == "player_turn"


def test_blunder_from_winning_into_unclear_still_stops(session):
    svc = service(base=0.98, after={"g2g4": 0.60})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "g2g4")
    assert svc.state(session, game)["status"] == "awaiting_reason"


def _bad_move_and_retry(svc, session, game, uci):
    svc.player_move(session, game, uci)
    svc.submit_reason(session, game, "because", "claude-sonnet-5-5")
    svc.continue_game(session, game, retry=True)


def test_coach_sees_earlier_attempts_at_this_position(session):
    svc = service(blunders={"f2f3", "g2g4"})
    game = svc.new_game(session, "white")
    _bad_move_and_retry(svc, session, game, "f2f3")
    svc.player_move(session, game, "g2g4")
    svc.submit_reason(session, game, "attacking", "claude-sonnet-5-5")
    history = FakeCoach.last["history"]
    assert [h["move_san"] for h in history] == ["f3"]
    assert history[0]["same_position"] is True
    assert history[0]["outcome"] == "retried"
    assert history[0]["coach_said"] == "about f3"


def test_first_retry_does_not_reveal(session):
    svc = service(blunders={"f2f3", "g2g4"})
    game = svc.new_game(session, "white")
    _bad_move_and_retry(svc, session, game, "f2f3")
    svc.player_move(session, game, "g2g4")
    svc.submit_reason(session, game, "x", "claude-sonnet-5-5")
    assert FakeCoach.last["reveal"] is False


def test_answer_revealed_after_two_retries(session):
    svc = service(blunders={"f2f3", "g2g4", "h2h4"})
    game = svc.new_game(session, "white")
    _bad_move_and_retry(svc, session, game, "f2f3")
    _bad_move_and_retry(svc, session, game, "g2g4")
    svc.player_move(session, game, "h2h4")
    svc.submit_reason(session, game, "what is the right move?", "claude-sonnet-5-5")
    assert FakeCoach.last["reveal"] is True
    ex = svc.state(session, game)["coach_log"][-1]
    assert ex["revealed"] is True and ex["best_move_uci"]


def test_show_me_button(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.submit_reason(session, game, "x", "claude-sonnet-5-5")
    svc.reveal(session, game, "claude-sonnet-5-5")
    ex = svc.state(session, game)["coach_log"][-1]
    assert ex["revealed"] is True
    assert ex["reveal_reply"].startswith("best is ")
    assert ex["best_move_uci"] == chess.Board().parse_san(ex["reveal_reply"][8:]).uci()
    purposes = sorted(r.purpose for r in session.scalars(select(LlmUsage)))
    assert purposes == ["label", "reply", "reveal"]
    # After taking the move back, the board is on the position the arrow belongs to.
    svc.continue_game(session, game, retry=True)
    state = svc.state(session, game)
    assert state["fen"] == chess.STARTING_FEN and state["coach_log"][-1]["best_move_uci"]


# --- feedback round 2 -------------------------------------------------------------------


def test_skip_question_and_retry(session):
    FakeCoach.calls = 0
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.continue_game(session, game, retry=True)  # straight from the question
    state = svc.state(session, game)
    assert FakeCoach.calls == 0
    assert state["status"] == "player_turn" and state["moves"] == []
    assert state["coach_log"][-1]["skipped"] is True
    assert state["coach_log"][-1]["quality"] == "blunder"  # shown once you've moved on


def test_skip_question_and_keep_move(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.continue_game(session, game, retry=False)
    state = svc.state(session, game)
    assert state["status"] == "player_turn" and len(state["moves"]) == 2


def test_log_carries_the_position_for_the_arrow(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.submit_reason(session, game, "x", "claude-sonnet-5-5")
    svc.reveal(session, game, "claude-sonnet-5-5")
    svc.continue_game(session, game, retry=True)
    ex = svc.state(session, game)["coach_log"][-1]
    assert ex["fen_before"] == chess.STARTING_FEN  # frontend shows the arrow only here
    svc.player_move(session, game, "e2e4")
    assert svc.state(session, game)["fen"] != ex["fen_before"]  # so it disappears now


@pytest.mark.parametrize(
    ("color", "result", "expected"),
    [
        ("white", "1-0", "win"),
        ("white", "0-1", "loss"),
        ("black", "0-1", "win"),
        ("black", "1/2-1/2", "draw"),
    ],
)
def test_outcome_for_player(session, color, result, expected):
    from backend.game_service import _outcome_for_player
    from core.infrastructure.postgresql.models import Game

    assert _outcome_for_player(Game(player_color=color, result=result)) == expected


def test_checkmate_reports_win_for_player(session):
    svc = service()
    script = iter(["f2f3", "g2g4"])
    svc.engines.opponent.play = lambda board: chess.Move.from_uci(next(script))
    game = svc.new_game(session, "black")
    svc.player_move(session, game, "e7e5")
    svc.player_move(session, game, "d8h4")
    assert svc.state(session, game)["outcome_for_player"] == "win"


# --- feedback round 3 -------------------------------------------------------------------


def test_skip_takeback_of_good_move_asks_first(session):
    svc = service(check_rate=1.0)  # good move, sampled for a check
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4")
    svc.continue_game(session, game, retry=True)
    state = svc.state(session, game)
    assert state["status"] == "confirm_takeback"
    assert state["moves"] == ["e4"]  # nothing taken back yet
    assert state["coach_log"][-1]["quality"] == "good"  # now it can be told


def test_confirm_keep_good_move(session):
    svc = service(check_rate=1.0)
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4")
    svc.continue_game(session, game, retry=True)
    svc.continue_game(session, game, retry=False)
    state = svc.state(session, game)
    assert state["status"] == "player_turn" and len(state["moves"]) == 2


def test_force_takeback_of_good_move(session):
    svc = service(check_rate=1.0)
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4")
    svc.continue_game(session, game, retry=True)
    svc.continue_game(session, game, retry=True, force=True)
    assert svc.state(session, game)["moves"] == []


def test_bad_move_skip_takeback_needs_no_confirmation(session):
    svc = service(blunders={"f2f3"})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.continue_game(session, game, retry=True)
    assert svc.state(session, game)["status"] == "player_turn"


# --- rating (PLAN D26) ------------------------------------------------------------------


def _fools_mate_win(svc, session, rated, takeback_first=False):
    """Player is black and mates with 1.f3 e5 2.g4 Qh4#. Optionally takes back a move first."""
    script = iter(["f2f3", "g2g4"])
    svc.engines.opponent.play = lambda board: chess.Move.from_uci(next(script))
    game = svc.new_game(session, "black", rated=rated)
    if takeback_first:
        svc.engines.judge.after = {"a7a6": 0.1}  # a blunder, so the coach asks
        svc.player_move(session, game, "a7a6")
        svc.continue_game(session, game, retry=True)
        svc.engines.judge.after = {}
    svc.player_move(session, game, "e7e5")
    svc.player_move(session, game, "d8h4")
    return game


def test_starting_rating_and_bot_match_it(session):
    svc = service()
    assert svc.rating(session) == {"rating": 400, "rated_games": 0, "provisional": True}
    assert svc.new_game(session, "white").bot_elo == 400


def test_rated_win_raises_rating_and_next_bot(session):
    svc = service()
    game = _fools_mate_win(svc, session, rated=True)
    state = svc.state(session, game)
    assert state["rating_change"]["before"] == 400
    assert state["rating_change"]["after"] == 424
    assert svc.rating(session)["rating"] == 424
    assert svc.new_game(session, "white").bot_elo == 424  # opponent keeps up


def test_casual_game_leaves_rating_alone(session):
    svc = service()
    game = _fools_mate_win(svc, session, rated=False)
    assert svc.state(session, game)["rating_change"] is None
    assert svc.rating(session)["rating"] == 400


def test_takeback_halves_a_win_and_is_reported(session):
    svc = service()
    game = _fools_mate_win(svc, session, rated=True, takeback_first=True)
    change = svc.state(session, game)["rating_change"]
    assert change["takebacks"] == 1
    assert change["delta"] == round(24 * (2 / 3))


def test_rated_resignation_is_a_loss(session):
    svc = service()
    game = svc.new_game(session, "white", rated=True)
    svc.resign(session, game)
    assert svc.rating(session)["rating"] == 376
