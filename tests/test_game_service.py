"""Game flow with fake engines: no Stockfish, no Maia, no API spend."""

import random

import chess
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.game_service import MAX_THINK_MS, Engines, GameError, GameService, Settings
from core.infrastructure.analysis.warning import ALLOWS_MATE, WarningSettings
from core.infrastructure.engines.stockfish import Evaluation
from core.infrastructure.postgresql.models import Base, Move


class FakeJudge:
    """White's eval is `base` win prob and `base_cp`. A move listed in `after` sets the mover's
    evaluation to `win_prob`, `(win_prob, cp)` or `(win_prob, cp, mate_in)`."""

    def __init__(self, after=None, base=0.5, base_cp=0):
        self.after = after or {}
        self.base = base
        self.base_cp = base_cp

    def evaluate(self, board, pov, lines=1):
        wp, cp, mate = self.base, self.base_cp, None  # white's view
        if board.move_stack and board.peek().uci() in self.after:
            spec = self.after[board.peek().uci()]
            spec = spec if isinstance(spec, tuple) else (spec,)
            m_wp, m_cp, m_mate = (*spec, *(0, None)[len(spec) - 1 :])  # pad the defaults
            if board.turn == chess.WHITE:  # black just moved: convert to white's view
                m_wp, m_cp, m_mate = 1 - m_wp, -m_cp, None if m_mate is None else -m_mate
            wp, cp, mate = m_wp, m_cp, m_mate
        if pov != chess.WHITE:
            wp, cp, mate = 1 - wp, -cp, None if mate is None else -mate
        best = next(iter(board.legal_moves), None)
        return Evaluation(pov, wp, None if mate else cp, mate, best, [best] if best else [])


class FakeOpponent:
    seed = 0

    def set_strength(self, elo, temperature=1.0):
        pass

    def play(self, board):
        return min(board.legal_moves, key=lambda m: m.uci())


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def service(after=None, base=0.5, base_cp=0):
    return GameService(
        Engines(FakeJudge(after, base, base_cp), FakeOpponent()),
        Settings(
            bot_elo=400,
            bot_temperature=1.0,
            spend_cap_usd=5.0,
            warning=WarningSettings(mate_depth=3, min_cp_drop=250, still_winning=0.85),
        ),
        rng=random.Random(0),
    )


def test_good_move_bot_replies(session):
    svc = service()
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4")
    state = svc.state(session, game)
    assert state["status"] == "player_turn"
    assert len(state["moves"]) == 2  # player + bot
    assert state["last_move"]["by"] == "bot"
    assert state["warning"] is None


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
    assert state["outcome_for_player"] == "win"


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


# --- quiet play (PLAN D27) ---------------------------------------------------------------


def test_material_blunder_warns_and_bot_waits(session):
    svc = service(after={"f2f3": (0.2, -300)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    state = svc.state(session, game)
    assert state["status"] == "warned"
    assert state["moves"] == ["f3"]  # bot has not moved
    assert state["warning"].startswith("⚠")
    assert state["warnings"] == 1


def test_cannot_move_while_warned(session):
    svc = service(after={"f2f3": (0.2, -300)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    with pytest.raises(GameError, match="not your turn"):
        svc.player_move(session, game, "e2e4")


def test_take_back_after_warning(session):
    svc = service(after={"f2f3": (0.2, -300)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.answer_warning(session, game, take_back=True)
    state = svc.state(session, game)
    assert state["status"] == "player_turn"
    assert state["moves"] == [] and state["fen"] == chess.STARTING_FEN
    assert state["warning"] is None
    move = session.scalar(select(Move).where(Move.by == "player"))
    assert move.taken_back and move.warning_outcome == "took_back"


def test_keep_after_warning_lets_bot_move(session):
    svc = service(after={"f2f3": (0.2, -300)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.answer_warning(session, game, take_back=False)
    state = svc.state(session, game)
    assert state["status"] == "player_turn" and len(state["moves"]) == 2
    assert session.scalar(select(Move.warning_outcome).where(Move.by == "player")) == "kept"


def test_kept_problem_is_not_warned_again(session):
    # Game 47: one unresolved problem was warned about on six moves in a row.
    svc = service(after={"f2f3": (0.2, -300), "g2g4": (0.2, -320)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.answer_warning(session, game, take_back=False)
    svc.player_move(session, game, "g2g4")  # still -3, not worse: quiet
    assert svc.state(session, game)["status"] == "player_turn"
    evals = session.scalars(select(Move.eval_cp_after).where(Move.by == "player"))
    assert list(evals) == [-300, -320]


def test_new_blunder_on_top_of_a_kept_problem_warns(session):
    svc = service(after={"f2f3": (0.2, -300), "g2g4": (0.0, -900)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    svc.answer_warning(session, game, take_back=False)
    svc.player_move(session, game, "g2g4")
    assert svc.state(session, game)["status"] == "warned"


def test_answer_warning_needs_a_warning(session):
    svc = service()
    game = svc.new_game(session, "white")
    with pytest.raises(GameError, match="no warning"):
        svc.answer_warning(session, game, take_back=True)


def test_mistake_below_threshold_is_silent(session):
    # 0.50 -> 0.35 is a "blunder" by win-prob (D6) but only 150 cp: not obvious, no warning.
    svc = service(after={"g2g4": (0.35, -150)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "g2g4")
    assert svc.state(session, game)["status"] == "player_turn"


def test_no_warning_while_still_clearly_winning(session):
    # Game 7's Qxg4: dropping material from +9 to +6 still leaves you winning.
    svc = service(base=0.98, base_cp=900, after={"g2g4": (0.9, 600)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "g2g4")
    assert svc.state(session, game)["status"] == "player_turn"


def test_unavoidable_mate_is_not_warned(session):
    # Game 50: every legal move allowed mate; the engine's best move does too, so stay quiet.
    best = next(iter(chess.Board().legal_moves)).uci()
    svc = service(after={"f2f3": (0.0, 0, -2), best: (0.0, 0, -2)})
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    assert svc.state(session, game)["status"] == "player_turn"


def test_allowing_mate_warns(session):
    svc = service(after={"f2f3": (0.0, 0, -2)})  # mover gets mated in 2
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "f2f3")
    assert svc.state(session, game)["warning"] == ALLOWS_MATE


# --- think time (PLAN D30) ---------------------------------------------------------------


def test_think_time_stored_and_capped(session):
    svc = service()
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4", think_ms=4200)
    svc.player_move(session, game, "d2d4", think_ms=99_999_999)
    times = session.scalars(select(Move.think_ms).where(Move.by == "player").order_by(Move.id))
    assert list(times) == [4200, MAX_THINK_MS]
    assert session.scalar(select(Move.think_ms).where(Move.by == "bot")) is None


def test_think_time_optional(session):
    svc = service()
    game = svc.new_game(session, "white")
    svc.player_move(session, game, "e2e4")
    assert session.scalar(select(Move.think_ms).where(Move.by == "player")) is None


# --- rating (PLAN D26) ------------------------------------------------------------------


def _fools_mate_win(svc, session, rated, takeback_first=False):
    """Player is black and mates with 1.f3 e5 2.g4 Qh4#. Optionally takes back a move first."""
    script = iter(["f2f3", "g2g4"])
    svc.engines.opponent.play = lambda board: chess.Move.from_uci(next(script))
    game = svc.new_game(session, "black", rated=rated)
    if takeback_first:
        svc.engines.judge.after = {"a7a6": (0.1, -400)}  # a blunder, so it warns
        svc.player_move(session, game, "a7a6")
        svc.answer_warning(session, game, take_back=True)
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
