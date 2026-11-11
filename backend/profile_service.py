"""Playstyle profile (PLAN D31): patterns with trends, think time, where games fall apart.

Every number here is counted in Python from stored moves (D1); no LLM is involved, so the page
is free to open. Games flagged `exclude_from_profile` are skipped by every statistic but still
listed, marked, so their reviews can be reopened.

As in the review, every move the player made counts, including ones taken back after a warning
(user feedback 6 Nov 2026); only development uses kept moves.
"""

from __future__ import annotations

import statistics
from collections import Counter

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.game_service import _outcome_for_player
from backend.review_service import _as_pattern_move, _player_moves
from core.infrastructure.analysis.patterns import BAD, PATTERNS, PlayerMove, count_patterns
from core.infrastructure.coach.traps import Trap
from core.infrastructure.postgresql.models import CoachExchange, Game, GameReview, Move

WINDOW = 10  # trend = the last WINDOW games against the WINDOW before (D31)
MIN_OPPORTUNITIES = 10  # below this a rate isn't shown as a strength/weakness or trend
MIN_TIMING_MOVES = 20  # risk R2: a think-time split needs this many moves to be shown
OPENING_MOVES = 10  # D31: the first 10 moves each
ENDGAME_MATERIAL = 13  # D31: per side, in points of non-pawn material
AHEAD, BEHIND = 0.65, 0.35  # D31: win chance before the move

# Traps only the player's own answers can show (D29): the engine can't see a missing plan.
ANSWER_ONLY_TRAPS = {Trap.HOPE_CHESS, Trap.NO_PLAN, Trap.TUNNEL_VISION}
TRAP_LABELS = {
    Trap.IGNORED_THREAT: "Didn't check their threat",
    Trap.LEFT_PIECE_UNDEFENDED: "Left a piece undefended",
    Trap.MISSED_CAPTURE: "Missed a capture",
    Trap.HOPE_CHESS: "Hope chess (hoping they won't see it)",
    Trap.NO_PLAN: "Moved without a plan",
    Trap.TUNNEL_VISION: "Tunnel vision on one idea",
}


def phase(fen: str) -> str:
    """opening = first OPENING_MOVES moves each; endgame = queens off, or each side down to
    ENDGAME_MATERIAL points of non-pawn material; middlegame otherwise."""
    board = chess.Board(fen)
    if board.fullmove_number <= OPENING_MOVES:
        return "opening"
    if not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(chess.QUEEN, chess.BLACK):
        return "endgame"
    values = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}

    def material(color: chess.Color) -> int:
        return sum(len(board.pieces(t, color)) * v for t, v in values.items())

    if material(chess.WHITE) <= ENDGAME_MATERIAL and material(chess.BLACK) <= ENDGAME_MATERIAL:
        return "endgame"
    return "middlegame"


def eval_state(win_prob_before: float | None) -> str:
    wp = 0.5 if win_prob_before is None else win_prob_before
    return "ahead" if wp >= AHEAD else "behind" if wp <= BEHIND else "level"


def _median_s(moves: list[PlayerMove]) -> dict:
    xs = [m.think_ms / 1000 for m in moves if m.think_ms is not None]
    return {
        "moves": len(xs),
        "median_s": round(statistics.median(xs), 1) if len(xs) >= MIN_TIMING_MOVES else None,
    }


def _rate(hits: int, opportunities: int) -> float | None:
    return round(hits / opportunities, 3) if opportunities else None


def _counts(c) -> dict:
    return {
        "hits": c.hits,
        "opportunities": c.opportunities,
        "rate": _rate(c.hits, c.opportunities),
    }


def _split(moves: list[PlayerMove], key) -> dict:
    """Bad-move rate (mistakes + blunders per move) and think time for each group."""
    groups: dict[str, list[PlayerMove]] = {}
    for m in moves:
        if m.quality is not None:
            groups.setdefault(key(m), []).append(m)
    out = {}
    for name, ms in groups.items():
        bad = sum(1 for m in ms if m.quality in BAD)
        out[name] = {
            "moves": len(ms),
            "bad_moves": bad,
            "bad_rate": _rate(bad, len(ms)),
            "think": _median_s(ms),
        }
    return out


class ProfileService:
    def profile(self, session: Session) -> dict:
        finished = list(
            session.scalars(
                select(Game)
                .where(Game.status == "finished")
                .options(selectinload(Game.moves))
                .order_by(Game.id)
            )
        )
        counted = [g for g in finished if not g.exclude_from_profile]
        moves_by_game = {g.id: [_as_pattern_move(m) for m in _player_moves(g)] for g in counted}
        all_moves = [m for ms in moves_by_game.values() for m in ms]
        recent = counted[-WINDOW:]
        previous = counted[-2 * WINDOW : -WINDOW]

        def window(games: list[Game]):
            return count_patterns({g.id: moves_by_game[g.id] for g in games})

        totals, now, before = window(counted), window(recent), window(previous)
        patterns = []
        for p in PATTERNS:
            r, b = now[p.key], before[p.key]
            trend = (
                round(r.rate - b.rate, 3)
                if r.opportunities >= MIN_OPPORTUNITIES and b.opportunities >= MIN_OPPORTUNITIES
                else None
            )
            patterns.append(
                {
                    "key": p.key,
                    "strength": p.strength,
                    "weakness": p.weakness,
                    "all": _counts(totals[p.key]),
                    "recent": _counts(r),
                    "previous": _counts(b),
                    "trend": trend,
                }
            )

        return {
            "games_counted": len(counted),
            "games_excluded": len(finished) - len(counted),
            "window": WINDOW,
            "min_opportunities": MIN_OPPORTUNITIES,
            "patterns": patterns,
            "headline": _headline(patterns),
            "timing": self._timing(all_moves),
            "breakdowns": {
                "phase": _split(all_moves, lambda m: phase(m.fen_before)),
                "color": _split(
                    all_moves, lambda m: "white" if chess.Board(m.fen_before).turn else "black"
                ),
                "eval_state": _split(all_moves, lambda m: eval_state(m.win_prob_before)),
            },
            "traps": self._traps(session, [g.id for g in counted]),
            "rating": [
                {
                    "game_id": g.id,
                    "date": g.created_at.date().isoformat(),
                    "rating": g.rating_after,
                }
                for g in finished
                if g.rated and g.rating_after is not None
            ],
            "games": self._game_list(session, finished),
        }

    @staticmethod
    def _timing(moves: list[PlayerMove]) -> dict:
        """Median think time (D30) by move quality, phase, and whether they had just threatened
        something. Splits under MIN_TIMING_MOVES moves have a count but no median (R2)."""
        timed = [m for m in moves if m.think_ms is not None and m.quality is not None]
        by_quality = {
            q: _median_s([m for m in timed if m.quality == q])
            for q in ("good", "inaccuracy", "mistake", "blunder")
        }
        by_phase = {
            ph: _median_s([m for m in timed if phase(m.fen_before) == ph])
            for ph in ("opening", "middlegame", "endgame")
        }
        threatened = [m for m in timed if (m.facts or {}).get("threats_they_had")]
        quiet = [m for m in timed if not (m.facts or {}).get("threats_they_had")]
        return {
            "timed_moves": len(timed),
            "min_moves": MIN_TIMING_MOVES,
            "by_quality": by_quality,
            "ok_vs_bad": {
                "ok": _median_s([m for m in timed if m.quality not in BAD]),
                "bad": _median_s([m for m in timed if m.quality in BAD]),
            },
            "by_phase": by_phase,
            "after_threat": {"threat": _median_s(threatened), "no_threat": _median_s(quiet)},
        }

    @staticmethod
    def _traps(session: Session, game_ids: list[int]) -> list[dict]:
        """Thinking traps from the player's own answers (labelled by D19), most common first."""
        if not game_ids:
            return []
        rows = session.scalars(
            select(CoachExchange.trap)
            .join(Move, CoachExchange.move_id == Move.id)
            .where(Move.game_id.in_(game_ids), CoachExchange.trap.is_not(None))
        )
        counts = Counter(t for t in rows if t in TRAP_LABELS)
        return [
            {
                "trap": t,
                "label": TRAP_LABELS[Trap(t)],
                "count": n,
                "answers_only": Trap(t) in ANSWER_ONLY_TRAPS,
            }
            for t, n in counts.most_common()
        ]

    @staticmethod
    def _game_list(session: Session, games: list[Game]) -> list[dict]:
        reviewed = set(session.scalars(select(GameReview.game_id)))
        out = []
        for g in reversed(games):
            mine = _player_moves(g)
            out.append(
                {
                    "id": g.id,
                    "date": g.created_at.date().isoformat(),
                    "color": g.player_color,
                    "outcome": _outcome_for_player(g),
                    "end_reason": g.end_reason,
                    "rated": g.rated,
                    "rating_delta": (
                        g.rating_after - g.rating_before if g.rating_after is not None else None
                    ),
                    "opponent": g.bot_elo,
                    "moves": sum(1 for m in mine if not m.taken_back),
                    "mistakes": sum(1 for m in mine if m.quality in BAD and not m.taken_back),
                    "caught": sum(1 for m in mine if m.warning and m.taken_back),
                    "has_summary": g.id in reviewed,
                    "excluded": g.exclude_from_profile,
                }
            )
        return out


def _headline(patterns: list[dict]) -> dict:
    """Strongest and weakest pattern over the last WINDOW games, among patterns with enough
    opportunities. Plain arithmetic, no LLM: 'insights first' without inventing anything."""
    rated = [p for p in patterns if p["recent"]["opportunities"] >= MIN_OPPORTUNITIES]
    if len(rated) < 2:
        return {"strength": None, "weakness": None}
    top = max(rated, key=lambda p: p["recent"]["rate"])
    low = min(rated, key=lambda p: p["recent"]["rate"])
    return {"strength": top["key"], "weakness": low["key"] if low is not top else None}
