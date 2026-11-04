"""Game flow: the coached 'why did you play that?' loop (PLAN D3).

player_turn --(player move, coach triggered)--> awaiting_reason
awaiting_reason --(reason submitted, coach replies)--> coach_replied
coach_replied --(retry)--> player_turn  (player's move taken back; bot hasn't moved yet)
coach_replied --(continue)--> bot moves --> player_turn
player_turn --(player move, no coach)--> bot moves --> player_turn
any --(game over / resign)--> finished
"""

from __future__ import annotations

import os
import random
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

import chess
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.infrastructure.analysis.move_review import MoveFacts, review_move
from core.infrastructure.coach.coach import Coach, CoachResult, Usage
from core.infrastructure.coach.pricing import cache_tokens
from core.infrastructure.postgresql.db import month_spend_usd
from core.infrastructure.postgresql.models import CoachExchange, Game, LlmUsage, Move
from core.infrastructure.rating import PROVISIONAL_GAMES, bot_elo_for, update

QUESTION = "Why did you play {san}?"  # same wording for mistakes and good-move checks
QUALITY_ORDER = ["good", "inaccuracy", "mistake", "blunder"]


class GameError(Exception):
    """A request that doesn't fit the game's current state (HTTP 409/400)."""


@dataclass
class Settings:
    bot_elo: int = int(os.environ.get("BOT_ELO", "400"))  # starting rating, before any rated game
    bot_temperature: float = float(os.environ.get("BOT_TEMPERATURE", "1.0"))
    good_move_check_rate: float = float(os.environ.get("GOOD_MOVE_CHECK_RATE", "0.125"))
    # Stop on mistakes and blunders only (game 7: stopping on inaccuracies nagged constantly).
    coach_min_quality: str = os.environ.get("COACH_MIN_QUALITY", "mistake")
    # Never stop a player whose move still leaves them clearly winning (game 7: Qxg4, which won
    # a knight, was stopped at 98% -> 91%).
    still_winning: float = float(os.environ.get("COACH_STILL_WINNING", "0.85"))
    # After this many retries of the same position, the coach gives the answer.
    reveal_after_retries: int = int(os.environ.get("REVEAL_AFTER_RETRIES", "2"))
    spend_cap_usd: float = float(os.environ.get("SPEND_CAP_USD", "5"))


@dataclass
class Engines:
    """One Stockfish judge and one Maia opponent per process, shared behind a lock."""

    judge: object
    opponent: object
    lock: threading.Lock = field(default_factory=threading.Lock)


class GameService:
    def __init__(
        self,
        engines: Engines,
        settings: Settings | None = None,
        coach_factory: Callable[[str], Coach] = Coach,
        rng: random.Random | None = None,
    ):
        self.engines = engines
        self.settings = settings or Settings()
        self.coach_factory = coach_factory
        self.rng = rng or random.Random()

    # --- helpers --------------------------------------------------------------------

    @staticmethod
    def board(game: Game) -> chess.Board:
        board = chess.Board()
        for m in game.moves:
            if not m.taken_back:
                board.push_uci(m.uci)
        return board

    @staticmethod
    def _active(game: Game) -> list[Move]:
        return [m for m in game.moves if not m.taken_back]

    def _player_color(self, game: Game) -> chess.Color:
        return chess.WHITE if game.player_color == "white" else chess.BLACK

    def _pending_exchange(self, game: Game) -> CoachExchange:
        last = self._active(game)[-1] if self._active(game) else None
        if last is None or last.by != "player" or last.exchange is None:
            raise GameError("no coach question is pending")
        return last.exchange

    def rating(self, session: Session) -> dict:
        """Current rating = the result of the latest finished rated game, else the start."""
        last = session.scalar(
            select(Game.rating_after)
            .where(Game.rated, Game.rating_after.is_not(None))
            .order_by(Game.id.desc())
            .limit(1)
        )
        count = session.scalar(
            select(func.count(Game.id)).where(Game.rated, Game.rating_after.is_not(None))
        )
        return {
            "rating": last if last is not None else self.settings.bot_elo,
            "rated_games": count or 0,
            "provisional": (count or 0) < PROVISIONAL_GAMES,
        }

    def _apply_rating(self, session: Session, game: Game) -> None:
        if not game.rated or game.rating_after is not None or game.result is None:
            return
        current = self.rating(session)
        score = {"win": 1.0, "draw": 0.5, "loss": 0.0}[_outcome_for_player(game)]
        takebacks = sum(1 for m in game.moves if m.by == "player" and m.taken_back)
        change = update(current["rating"], game.bot_elo, score, current["rated_games"], takebacks)
        game.rating_before, game.rating_after = change.before, change.after
        game.rating_weight = change.weight

    @staticmethod
    def _history(game: Game, current: Move, limit: int = 6) -> list[dict]:
        """Earlier coach replies in this game, so the coach stays consistent (game 7)."""
        out = []
        for m in game.moves:
            ex = m.exchange
            if m.id == current.id or m.by != "player" or ex is None or not ex.reply:
                continue
            out.append(
                {
                    "move_san": m.san,
                    "same_position": m.fen_before == current.fen_before,
                    "engine_rating": m.quality,
                    "player_said": ex.player_reason,
                    "coach_said": ex.reply,
                    "best_move_revealed": ex.reveal_reply,
                    "outcome": ex.outcome,
                }
            )
        return out[-limit:]

    @staticmethod
    def _retries_here(game: Game, current: Move) -> int:
        return sum(
            1
            for m in game.moves
            if m.id != current.id
            and m.fen_before == current.fen_before
            and m.exchange is not None
            and m.exchange.outcome == "retried"
        )

    def _finish_if_over(self, session: Session, game: Game, board: chess.Board) -> bool:
        outcome = board.outcome(claim_draw=True)
        if outcome is None:
            return False
        game.status = "finished"
        game.result = outcome.result()
        game.end_reason = outcome.termination.name.lower()
        self._apply_rating(session, game)
        return True

    def _bot_move(self, session: Session, game: Game) -> None:
        board = self.board(game)
        with self.engines.lock:
            self.engines.opponent.set_strength(game.bot_elo, game.bot_temperature)
            move = self.engines.opponent.play(board)
        session.add(
            Move(game=game, by="bot", uci=move.uci(), san=board.san(move), fen_before=board.fen())
        )
        board.push(move)
        if not self._finish_if_over(session, game, board):
            game.status = "player_turn"

    def _should_ask(self, quality: str, win_prob_after: float) -> tuple[bool, str]:
        bad = QUALITY_ORDER.index(quality) >= QUALITY_ORDER.index(self.settings.coach_min_quality)
        if bad and win_prob_after < self.settings.still_winning:
            return True, "mistake"
        if quality != "good":
            return False, ""  # imperfect but not worth stopping for
        if self.rng.random() < self.settings.good_move_check_rate:
            return True, "good_move_check"
        return False, ""

    # --- actions --------------------------------------------------------------------

    def new_game(self, session: Session, color: str, rated: bool = False) -> Game:
        if color == "random":
            color = self.rng.choice(["white", "black"])
        if color not in ("white", "black"):
            raise GameError("color must be white, black or random")
        # The bot always matches your current rating, rated game or not (PLAN D26).
        game = Game(
            player_color=color,
            rated=rated,
            bot_elo=bot_elo_for(self.rating(session)["rating"]),
            bot_temperature=self.settings.bot_temperature,
            status="player_turn",
        )
        session.add(game)
        session.flush()
        if color == "black":
            self._bot_move(session, game)
        session.commit()
        return game

    def player_move(self, session: Session, game: Game, uci: str) -> Game:
        if game.status != "player_turn":
            raise GameError(f"not your turn (status: {game.status})")
        board = self.board(game)
        if board.turn != self._player_color(game):
            raise GameError("not your turn")
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise GameError(f"bad move format: {uci}") from exc
        if move not in board.legal_moves:
            raise GameError(f"illegal move: {uci}")

        with self.engines.lock:
            facts, _ = review_move(self.engines.judge, board, move)
        record = Move(
            game=game,
            by="player",
            uci=uci,
            san=facts.move_san,
            fen_before=board.fen(),
            quality=facts.quality,
            win_prob_before=facts.win_prob_before,
            win_prob_after=facts.win_prob_after,
            facts=asdict(facts),
        )
        session.add(record)
        board.push(move)

        if self._finish_if_over(session, game, board):
            session.commit()
            return game
        ask, why = self._should_ask(facts.quality, facts.win_prob_after)
        if ask:
            session.add(CoachExchange(move=record, reason_asked=why))
            game.status = "awaiting_reason"
        else:
            self._bot_move(session, game)
        session.commit()
        return game

    def submit_reason(self, session: Session, game: Game, text: str, model: str) -> Game:
        if game.status != "awaiting_reason":
            raise GameError(f"no question pending (status: {game.status})")
        text = text.strip()
        if not text:
            raise GameError("tell the coach why you played it (any words are fine)")
        exchange = self._pending_exchange(game)
        move = exchange.move
        exchange.player_reason = text

        spent = month_spend_usd(session)
        if spent >= self.settings.spend_cap_usd:
            exchange.reply = (
                f"The coach is paused: this month's budget is used up "
                f"(${spent:.2f} of ${self.settings.spend_cap_usd:.2f}). That move was "
                f"rated {move.quality}. You can retry it or carry on."
            )
            exchange.reply_model = None
            exchange.offered_retry = move.quality != "good"
        else:
            # Raises on provider errors; status stays awaiting_reason so the player can resend.
            reveal = self._retries_here(game, move) >= self.settings.reveal_after_retries
            result: CoachResult = self.coach_factory(model).review(
                MoveFacts(**move.facts), text, self._history(game, move), reveal
            )
            exchange.revealed = reveal
            exchange.reply = result.reply
            exchange.reply_model = result.reply_model
            exchange.trap = result.trap.value
            exchange.proposed_trap_name = result.proposed_trap_name
            exchange.offered_retry = result.offer_retry
            session.flush()  # exchange.id is needed by the usage rows
            for u in result.usages:
                session.add(_usage_row(exchange, u))
        game.status = "coach_replied"
        session.commit()
        return game

    def continue_game(self, session: Session, game: Game, retry: bool, force: bool = False) -> Game:
        """Retry or keep the move. Allowed straight from the question too: answering the coach
        is optional (user feedback: having to type something to progress was a blocker).

        Skipping straight to a take-back on a GOOD move asks for confirmation first, revealing
        that it was good (user feedback: took back a good move without knowing). `force`
        takes it back anyway.
        """
        if game.status not in ("coach_replied", "awaiting_reason", "confirm_takeback"):
            raise GameError(f"nothing to continue (status: {game.status})")
        exchange = self._pending_exchange(game)
        if (
            retry
            and not force
            and game.status == "awaiting_reason"
            and exchange.move.quality == "good"
        ):
            game.status = "confirm_takeback"
            session.commit()
            return game
        if retry:
            exchange.outcome = "retried"
            exchange.move.taken_back = True
            game.status = "player_turn"
        else:
            exchange.outcome = "continued"
            self._bot_move(session, game)
        session.commit()
        return game

    def reveal(self, session: Session, game: Game, model: str) -> Game:
        """'Show me the best move': the coach names it and says why; the board draws it."""
        if game.status != "coach_replied":
            raise GameError(f"nothing to reveal (status: {game.status})")
        exchange = self._pending_exchange(game)
        if exchange.revealed:
            return game
        move = exchange.move
        spent = month_spend_usd(session)
        if spent >= self.settings.spend_cap_usd:
            best = (move.facts or {}).get("best_move_san")
            exchange.reveal_reply = f"The best move was {best}. (Coach paused: budget used up.)"
        else:
            result = self.coach_factory(model).explain_best(
                MoveFacts(**move.facts), self._history(game, move)
            )
            exchange.reveal_reply = result.reply
            session.flush()
            for u in result.usages:
                session.add(_usage_row(exchange, u))
        exchange.revealed = True
        session.commit()
        return game

    def resign(self, session: Session, game: Game) -> Game:
        if game.status == "finished":
            raise GameError("game already finished")
        game.status = "finished"
        game.result = "0-1" if game.player_color == "white" else "1-0"
        game.end_reason = "resignation"
        self._apply_rating(session, game)
        session.commit()
        return game

    # --- view -----------------------------------------------------------------------

    def state(self, session: Session, game: Game) -> dict:
        board = self.board(game)
        active = self._active(game)
        log = []
        # All moves, including taken-back ones: the advice must stay visible for the retry.
        for m in game.moves:
            if m.by == "player" and m.exchange is not None:
                ex = m.exchange
                log.append(
                    {
                        "move_san": m.san,
                        "question": QUESTION.format(san=m.san),
                        "player_reason": ex.player_reason,
                        "reply": ex.reply,
                        "reply_model": ex.reply_model,
                        # Revealed once the coach has replied or the player has moved on.
                        "quality": m.quality
                        if (ex.reply or ex.outcome or game.status == "confirm_takeback")
                        else None,
                        "skipped": ex.reply is None and ex.outcome is not None,
                        "fen_before": m.fen_before,  # the arrow belongs on this position only
                        "offer_retry": ex.offered_retry,
                        "taken_back": m.taken_back,
                        "revealed": ex.revealed,
                        "reveal_reply": ex.reveal_reply,
                        "best_move_uci": _best_uci(m) if ex.revealed else None,
                    }
                )
        last = active[-1] if active else None
        return {
            "id": game.id,
            "fen": board.fen(),
            "player_color": game.player_color,
            "status": game.status,
            "result": game.result,
            "end_reason": game.end_reason,
            "outcome_for_player": _outcome_for_player(game),
            "rated": game.rated,
            "bot_elo": game.bot_elo,
            "rating_change": (
                {
                    "before": game.rating_before,
                    "after": game.rating_after,
                    "delta": game.rating_after - game.rating_before,
                    "weight": game.rating_weight,
                    "takebacks": sum(1 for m in game.moves if m.by == "player" and m.taken_back),
                }
                if game.rating_after is not None
                else None
            ),
            "player_rating": self.rating(session),
            "moves": [m.san for m in active],
            "last_move": {"uci": last.uci, "by": last.by} if last else None,
            "coach_log": log,
            "spend": {
                "month_usd": round(month_spend_usd(session), 4),
                "cap_usd": self.settings.spend_cap_usd,
            },
        }


def _usage_row(exchange: CoachExchange, u: Usage) -> LlmUsage:
    read, w5, w1 = cache_tokens(u.usage)
    return LlmUsage(
        exchange_id=exchange.id,
        model=u.model,
        purpose=u.purpose,
        input_tokens=u.usage.get("input_tokens", 0),
        output_tokens=u.usage.get("output_tokens", 0),
        cache_read_tokens=read,
        cache_write_tokens=w5 + w1,
        cost_usd=u.cost_usd,
    )


def _best_uci(move: Move) -> str | None:
    san = (move.facts or {}).get("best_move_san")
    if not san:
        return None
    try:
        return chess.Board(move.fen_before).parse_san(san).uci()
    except ValueError:
        return None


def _outcome_for_player(game: Game) -> str | None:
    if game.result is None:
        return None
    if game.result == "1/2-1/2":
        return "draw"
    white_won = game.result == "1-0"
    return "win" if white_won == (game.player_color == "white") else "loss"
