"""End-of-game review (PLAN D28): what went well, the costliest mistakes, thinking patterns.

Everything except the coach's replies and the one summary is computed here from stored moves
(D1, D29, D30), so opening a review is instant and free. The summary is written once per game and
cached in `game_reviews`. Games flagged `exclude_from_profile` never count as history (D31).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.game_service import GameError, GameService, _outcome_for_player
from core.infrastructure.analysis.move_review import MoveFacts
from core.infrastructure.analysis.patterns import (
    BAD,
    PATTERNS,
    PlayerMove,
    count_patterns,
    highlights,
    think_medians,
)
from core.infrastructure.coach.coach import Coach, Usage
from core.infrastructure.coach.pricing import cache_tokens
from core.infrastructure.postgresql.db import month_spend_usd
from core.infrastructure.postgresql.models import CoachExchange, Game, GameReview, LlmUsage, Move

HISTORY_GAMES = 10  # "your usual" = this many previous finished, included games
MISTAKES_SHOWN = 3
LINE_PLIES = 4  # how far the refutation is shown


def _player_moves(game: Game) -> list[Move]:
    """Every move the player made, including ones taken back after a warning: the decision was
    theirs (user feedback: 'no blunders' was hollow when the warning had caught some)."""
    return [m for m in game.moves if m.by == "player"]


def _warnings(game: Game) -> dict:
    warned = [m for m in _player_moves(game) if m.warning]
    return {
        "shown": len(warned),
        "taken_back": sum(1 for m in warned if m.warning_outcome == "took_back"),
        "kept": sum(1 for m in warned if m.warning_outcome == "kept"),
    }


def _as_pattern_move(m: Move) -> PlayerMove:
    return PlayerMove(
        m.id,
        m.game_id,
        m.san,
        m.uci,
        m.fen_before,
        m.quality,
        m.win_prob_before,
        m.win_prob_after,
        m.facts,
        m.think_ms,
        m.taken_back,
    )


def _played_anyway(m: Move) -> bool:
    """Kept after a warning about this exact move, whether on the spot or after taking it back
    and replaying it."""
    if m.taken_back:
        return False
    if m.warning_outcome == "kept":
        return True
    return any(
        o.warning and o.taken_back and o.fen_before == m.fen_before and o.uci == m.uci
        for o in m.game.moves
    )


def _line_uci(fen: str, first_uci: str, sans: list[str]) -> list[str]:
    """The played move followed by the opponent's best line, as UCI, stopping at anything that
    doesn't parse (the stored line is SAN from the position after the move)."""
    board = chess.Board(fen)
    board.push_uci(first_uci)
    out = [first_uci]
    for san in sans[:LINE_PLIES]:
        try:
            move = board.parse_san(san)
        except ValueError:
            break
        out.append(move.uci())
        board.push(move)
    return out


def _best_uci(fen: str, san: str | None) -> str | None:
    if not san:
        return None
    try:
        return chess.Board(fen).parse_san(san).uci()
    except ValueError:
        return None


class ReviewService:
    def __init__(self, games: GameService, coach_factory: Callable[..., Coach] = Coach):
        self.games = games
        self.coach_factory = coach_factory

    @property
    def spend_cap(self) -> float:
        return self.games.settings.spend_cap_usd

    # --- what the review is built from ------------------------------------------------------

    @staticmethod
    def mistakes(game: Game) -> list[Move]:
        """The costliest moves the engine calls a mistake or blunder, in game order. Includes
        moves taken back after a warning: the thinking behind them is what the review is for."""
        # The same move from the same position counts once (game 48: warned about O-O, took it
        # back, then played O-O anyway). The kept one stands for the pair.
        by_decision: dict[tuple[str, str], Move] = {}
        for m in _player_moves(game):
            if m.quality not in BAD:
                continue
            key = (m.fen_before, m.uci)
            if key not in by_decision or by_decision[key].taken_back:
                by_decision[key] = m
        bad = list(by_decision.values())
        bad.sort(key=lambda m: (m.win_prob_before or 0) - (m.win_prob_after or 0), reverse=True)
        return sorted(bad[:MISTAKES_SHOWN], key=lambda m: m.id)

    @staticmethod
    def _history_games(session: Session, game: Game) -> list[Game]:
        return list(
            session.scalars(
                select(Game)
                .where(
                    Game.id < game.id,
                    Game.status == "finished",
                    Game.exclude_from_profile.is_(False),
                )
                .order_by(Game.id.desc())
                .limit(HISTORY_GAMES)
            )
        )

    @staticmethod
    def _exchange(session: Session, move: Move) -> CoachExchange | None:
        return session.scalar(
            select(CoachExchange).where(
                CoachExchange.move_id == move.id, CoachExchange.reason_asked == "review"
            )
        )

    @staticmethod
    def _traps(session: Session, game_ids: list[int]) -> dict[str, int]:
        """Reasons the player gave (labelled by D19), from any coach exchange in these games."""
        if not game_ids:
            return {}
        rows = session.scalars(
            select(CoachExchange.trap)
            .join(Move, CoachExchange.move_id == Move.id)
            .where(Move.game_id.in_(game_ids), CoachExchange.trap.is_not(None))
        )
        return dict(Counter(t for t in rows if t != "none"))

    def numbers(self, session: Session, game: Game) -> dict:
        """The computed side of the review; also exactly what the summary is written from."""
        moves = [_as_pattern_move(m) for m in _player_moves(game)]
        history = self._history_games(session, game)
        history_moves = {g.id: [_as_pattern_move(m) for m in _player_moves(g)] for g in history}
        this = count_patterns({game.id: moves})
        usual = count_patterns(history_moves)
        # Warnings exist from P2a on; average over the history games that could have had them.
        warned_era = [g for g in history if any(m.eval_cp_after is not None for m in g.moves)]
        caught = [_warnings(g)["taken_back"] for g in warned_era]
        return {
            "result": _outcome_for_player(game),
            "end_reason": game.end_reason,
            "moves_played": len(moves),
            "history_games": len(history),
            "patterns": [
                {
                    "key": p.key,
                    "strength": p.strength,
                    "weakness": p.weakness,
                    "this_game": {
                        "hits": this[p.key].hits,
                        "opportunities": this[p.key].opportunities,
                    },
                    "usual": {
                        "hits": usual[p.key].hits,
                        "opportunities": usual[p.key].opportunities,
                    },
                }
                for p in PATTERNS
            ],
            # Blunders the in-game warning (D27) caught and the player took back.
            "warnings": {
                "this_game": _warnings(game),
                "usual_taken_back_per_game": round(sum(caught) / len(caught), 1)
                if caught
                else None,
            },
            "think_seconds": {
                "this_game": think_medians(moves),
                "usual": think_medians([m for ms in history_moves.values() for m in ms]),
            },
            "traps": {
                "this_game": self._traps(session, [game.id]),
                "usual": self._traps(session, [g.id for g in history]),
            },
            "highlights": [
                {"move_number": h.move_number, "san": h.san, "text": h.text}
                for h in highlights(moves)
            ],
            "mistakes": [
                {
                    "move_number": chess.Board(m.fen_before).fullmove_number,
                    "san": m.san,
                    "engine_rating": m.quality,
                    "taken_back_after_warning": bool(m.warning and m.taken_back),
                    "played_anyway_after_warning": _played_anyway(m),
                    "better_was": (m.facts or {}).get("best_move_san"),
                    "player_said": ex.player_reason if (ex := self._exchange(session, m)) else None,
                    "trap": ex.trap if ex else None,
                }
                for m in self.mistakes(game)
            ],
        }

    # --- view -------------------------------------------------------------------------------

    def review(self, session: Session, game: Game) -> dict:
        self._require_finished(game)
        numbers = self.numbers(session, game)
        by_id = {m.id: m for m in game.moves}
        moves = [_as_pattern_move(m) for m in _player_moves(game)]
        cached = session.scalar(select(GameReview).where(GameReview.game_id == game.id))
        return {
            "game_id": game.id,
            "player_color": game.player_color,
            "excluded": game.exclude_from_profile,
            "numbers": numbers,
            "highlights": [
                {
                    "move_id": h.move_id,
                    "move_number": h.move_number,
                    "san": h.san,
                    "text": h.text,
                    "fen_before": by_id[h.move_id].fen_before,
                    "line_uci": [by_id[h.move_id].uci],
                }
                for h in highlights(moves)
            ],
            "mistakes": [self._mistake_card(session, m) for m in self.mistakes(game)],
            "summary": cached.summary if cached else None,
            "summary_model": cached.model if cached else None,
        }

    def _mistake_card(self, session: Session, m: Move) -> dict:
        facts = m.facts or {}
        ex = self._exchange(session, m)
        answered = bool(ex and (ex.reply or ex.outcome == "skipped"))
        return {
            "move_id": m.id,
            "move_number": chess.Board(m.fen_before).fullmove_number,
            "san": m.san,
            "quality": m.quality,
            "caught_by_warning": bool(m.warning and m.taken_back),
            "played_anyway": _played_anyway(m),
            "question": f"Why did you play {m.san}?",
            "fen_before": m.fen_before,
            # Shown only once the player has answered or skipped: asking first, then showing
            # (the question stays neutral, as in D25).
            "their_line_uci": _line_uci(m.fen_before, m.uci, facts.get("their_best_line_san", []))
            if answered
            else [m.uci],
            "their_line_san": facts.get("their_best_line_san", [])[:LINE_PLIES] if answered else [],
            "best_move_san": facts.get("best_move_san") if answered else None,
            "best_uci": _best_uci(m.fen_before, facts.get("best_move_san")) if answered else None,
            "player_reason": ex.player_reason if ex else None,
            "reply": ex.reply if ex else None,
            "skipped": bool(ex and ex.outcome == "skipped"),
            "revealed": bool(ex and ex.revealed),
            "reveal_reply": ex.reveal_reply if ex else None,
        }

    # --- actions ------------------------------------------------------------------------------

    @staticmethod
    def _require_finished(game: Game) -> None:
        if game.status != "finished":
            raise GameError("the review opens when the game has finished")

    def _mistake(self, game: Game, move_id: int) -> Move:
        self._require_finished(game)
        for m in self.mistakes(game):
            if m.id == move_id:
                return m
        raise GameError("that move isn't one of this game's reviewed mistakes")

    def _history(self, session: Session, game: Game, current: Move) -> list[dict]:
        """Earlier review exchanges in this game, so the coach stays consistent (D22)."""
        out = []
        for m in self.mistakes(game):
            ex = self._exchange(session, m)
            if m.id != current.id and ex and ex.reply:
                out.append(
                    {
                        "move_san": m.san,
                        "same_position": False,
                        "engine_rating": m.quality,
                        "player_said": ex.player_reason,
                        "coach_said": ex.reply,
                        "best_move_revealed": ex.reveal_reply,
                        "outcome": None,
                    }
                )
        return out

    def _over_cap(self, session: Session) -> float | None:
        spent = month_spend_usd(session)
        return spent if spent >= self.spend_cap else None

    def answer(self, session: Session, game: Game, move_id: int, text: str, model: str) -> None:
        move = self._mistake(game, move_id)
        text = text.strip()
        if not text:
            raise GameError("say why you played it (any words are fine), or skip")
        ex = self._exchange(session, move) or CoachExchange(move_id=move.id, reason_asked="review")
        session.add(ex)
        ex.player_reason = text
        ex.outcome = None
        if (spent := self._over_cap(session)) is not None:
            ex.reply = (
                f"The coach is paused: this month's budget is used up (${spent:.2f} of "
                f"${self.spend_cap:.2f}). Your answer is saved."
            )
        else:
            result = self.coach_factory(model, after_game=True).review(
                MoveFacts(**move.facts), text, self._history(session, game, move)
            )
            ex.reply = result.reply
            ex.reply_model = result.reply_model
            ex.trap = result.trap.value
            ex.proposed_trap_name = result.proposed_trap_name
            ex.offered_retry = False
            session.flush()
            for u in result.usages:
                session.add(_usage_row(ex.id, u))
        session.commit()

    def skip(self, session: Session, game: Game, move_id: int) -> None:
        move = self._mistake(game, move_id)
        ex = self._exchange(session, move) or CoachExchange(move_id=move.id, reason_asked="review")
        session.add(ex)
        if not ex.reply:
            ex.outcome = "skipped"
        session.commit()

    def reveal(self, session: Session, game: Game, move_id: int, model: str) -> None:
        """'Why is that better?': the coach explains the best move (D23)."""
        move = self._mistake(game, move_id)
        ex = self._exchange(session, move)
        if ex is None or not (ex.reply or ex.outcome == "skipped"):
            raise GameError("answer or skip the question first")
        if ex.revealed:
            return
        if self._over_cap(session) is not None:
            best = (move.facts or {}).get("best_move_san")
            ex.reveal_reply = f"The best move was {best}. (Coach paused: budget used up.)"
        else:
            result = self.coach_factory(model, after_game=True).explain_best(
                MoveFacts(**move.facts), self._history(session, game, move)
            )
            ex.reveal_reply = result.reply
            session.flush()
            for u in result.usages:
                session.add(_usage_row(ex.id, u))
        ex.revealed = True
        session.commit()

    def summarise(self, session: Session, game: Game, model: str) -> None:
        """Write the summary once; later calls return the cached one at no cost."""
        self._require_finished(game)
        if session.scalar(select(GameReview.id).where(GameReview.game_id == game.id)):
            return
        if (spent := self._over_cap(session)) is not None:
            raise GameError(
                f"The coach is paused: this month's budget is used up "
                f"(${spent:.2f} of ${self.spend_cap:.2f})."
            )
        numbers = self.numbers(session, game)
        summary, usage = self.coach_factory(model, after_game=True).summarise(numbers)
        session.add(
            GameReview(game_id=game.id, model=model, summary=summary.model_dump(), numbers=numbers)
        )
        session.add(_usage_row(None, usage))
        session.commit()


def _usage_row(exchange_id: int | None, u: Usage) -> LlmUsage:
    read, w5, w1 = cache_tokens(u.usage)
    return LlmUsage(
        exchange_id=exchange_id,
        model=u.model,
        purpose=u.purpose,
        input_tokens=u.usage.get("input_tokens", 0),
        output_tokens=u.usage.get("output_tokens", 0),
        cache_read_tokens=read,
        cache_write_tokens=w5 + w1,
        cost_usd=u.cost_usd,
    )
