"""Game flow: quiet play with an engine-only blunder warning (PLAN D27).

player_turn --(player move, no warning)--> bot moves --> player_turn
player_turn --(player move, D27 warning)--> warned   (bot hasn't moved yet)
warned --(take back)--> player_turn
warned --(keep)--> bot moves --> player_turn
any --(game over / resign)--> finished

The "why did you play that?" questions moved to the end-of-game review (D28, P2b).
"""

from __future__ import annotations

import os
import random
import threading
from dataclasses import asdict, dataclass, field

import chess
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.infrastructure.analysis.move_review import analyse_move
from core.infrastructure.analysis.warning import (
    ALLOWS_MATE,
    WarningSettings,
    as_cp,
    blunder_warning,
    mate_unavoidable,
)
from core.infrastructure.postgresql.db import month_spend_usd
from core.infrastructure.postgresql.models import Game, Move
from core.infrastructure.rating import PROVISIONAL_GAMES, bot_elo_for, update

MAX_THINK_MS = 5 * 60 * 1000  # D30: a walk-away shouldn't distort the medians


class GameError(Exception):
    """A request that doesn't fit the game's current state (HTTP 409/400)."""


@dataclass
class Settings:
    bot_elo: int = int(os.environ.get("BOT_ELO", "400"))  # starting rating, before any rated game
    bot_temperature: float = float(os.environ.get("BOT_TEMPERATURE", "1.0"))
    spend_cap_usd: float = float(os.environ.get("SPEND_CAP_USD", "5"))
    # D27 thresholds: starting values, tuned from the stored warnings (PLAN risk R1).
    warning: WarningSettings = field(
        default_factory=lambda: WarningSettings(
            mate_depth=int(os.environ.get("WARN_MATE_DEPTH", "3")),
            min_cp_drop=int(os.environ.get("WARN_MIN_CP_DROP", "250")),
            still_winning=float(os.environ.get("WARN_STILL_WINNING", "0.85")),
        )
    )


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
        rng: random.Random | None = None,
    ):
        self.engines = engines
        self.settings = settings or Settings()
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

    def player_move(
        self, session: Session, game: Game, uci: str, think_ms: int | None = None
    ) -> Game:
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

        previous = next((m for m in reversed(self._active(game)) if m.by == "player"), None)
        with self.engines.lock:
            analysis = analyse_move(self.engines.judge, board, move)
        facts = analysis.facts
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
            think_ms=None if think_ms is None else max(0, min(int(think_ms), MAX_THINK_MS)),
            eval_cp_after=as_cp(analysis.after),
        )
        session.add(record)
        board_before = board.copy()
        board.push(move)

        if self._finish_if_over(session, game, board):
            session.commit()
            return game
        record.warning = blunder_warning(
            analysis.before,
            analysis.after,
            facts.pieces_left_hanging,
            self.settings.warning,
            accepted_cp=previous.eval_cp_after if previous else None,
        )
        if record.warning == ALLOWS_MATE:
            with self.engines.lock:
                if mate_unavoidable(self.engines.judge, board_before, analysis.before):
                    record.warning = None
        if record.warning:
            game.status = "warned"
        else:
            self._bot_move(session, game)
        session.commit()
        return game

    def answer_warning(self, session: Session, game: Game, take_back: bool) -> Game:
        """Take back the warned move (counts as a take-back for rating, D26) or keep it."""
        if game.status != "warned":
            raise GameError(f"no warning to answer (status: {game.status})")
        move = self._active(game)[-1]
        if take_back:
            move.warning_outcome = "took_back"
            move.taken_back = True
            game.status = "player_turn"
        else:
            move.warning_outcome = "kept"
            self._bot_move(session, game)
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
            # The current warning, while the game waits on it (D27).
            "warning": last.warning if game.status == "warned" and last else None,
            "warnings": sum(1 for m in game.moves if m.warning),
            "spend": {
                "month_usd": round(month_spend_usd(session), 4),
                "cap_usd": self.settings.spend_cap_usd,
            },
        }


def _outcome_for_player(game: Game) -> str | None:
    if game.result is None:
        return None
    if game.result == "1/2-1/2":
        return "draw"
    white_won = game.result == "1-0"
    return "win" if white_won == (game.player_color == "white") else "loss"
