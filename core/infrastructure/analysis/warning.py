"""The in-game blunder warning (PLAN D27): engine-only, instant, free.

"Obvious" means a concrete swing (a forced mate, or about a minor piece of material), measured in
centipawns rather than win probability (D6), because a win-prob drop also fires on quiet moves in
level positions. Never fires while the player is still clearly winning after the move.

The drop is measured from what the player had already accepted, not only from best play. Game 47:
6.Bd3 blocked the queen's defence of d4 (a real piece loss), the bot never took it, and every
later move that didn't fix d4 was warned about again (6 warnings for one problem). Now a problem
that's already on the board stays quiet; only making it worse warns.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from core.infrastructure.analysis.facts import VALUE
from core.infrastructure.engines.stockfish import Evaluation

MATE_CP = 10_000  # a forced mate counts as more material than any position can hold
PIECE_VALUE = {
    "pawn": VALUE[1],
    "knight": VALUE[2],
    "bishop": VALUE[3],
    "rook": VALUE[4],
    "queen": VALUE[5],
}
ALLOWS_MATE = "⚠ This allows checkmate."


@dataclass(frozen=True)
class WarningSettings:
    mate_depth: int = 3  # warn if the move allows mate in this many moves or fewer
    min_cp_drop: int = 250  # about a minor piece, from the accepted position
    still_winning: float = 0.85  # no warning while still at least this likely to win


def as_cp(ev: Evaluation) -> int:
    """Centipawns for `ev.pov`, with forced mates mapped to +/- (MATE_CP - distance)."""
    if ev.score_cp is not None:
        return ev.score_cp
    if not ev.mate_in:  # mate on the board (0); whoever is mated has win_prob 0
        return MATE_CP if ev.win_prob >= 0.5 else -MATE_CP
    sign = 1 if ev.mate_in > 0 else -1
    return sign * (MATE_CP - abs(ev.mate_in))


def blunder_warning(
    before: Evaluation,
    after: Evaluation,
    pieces_left_hanging: list[str],
    settings: WarningSettings,
    accepted_cp: int | None = None,
) -> str | None:
    """`before` is the position before the move (best play), `after` the position after it, both
    from the mover's point of view. `accepted_cp` is `as_cp` of the position the player's previous
    move left them in (None on their first move). Returns the one-line warning, or None."""
    if after.win_prob >= settings.still_winning:
        return None
    baseline = as_cp(before) if accepted_cp is None else min(as_cp(before), accepted_cp)
    already_mated = (before.mate_in is not None and before.mate_in < 0) or (
        baseline <= -(MATE_CP - 100)
    )
    allows_mate = after.mate_in is not None and -settings.mate_depth <= after.mate_in < 0
    if allows_mate and not already_mated:
        return ALLOWS_MATE
    drop = baseline - as_cp(after)
    if drop < settings.min_cp_drop:
        return None
    if after.mate_in is not None and after.mate_in < 0:  # a deeper forced mate: say so
        return ALLOWS_MATE
    return material_text(drop, pieces_left_hanging)


def mate_unavoidable(judge, board: chess.Board, before: Evaluation) -> bool:
    """True if even the engine's best move allows a forced mate, so the mate warning has nothing
    to offer. Game 50: in check with only Kc3/Ka4/Ka2 legal, all mated, and each was warned
    about, because the search before the move hadn't seen the mate yet but the one after it did.
    `board` is the position before the move."""
    if before.mate_in is not None and before.mate_in < 0:
        return True
    if before.best_move is None:
        return True
    trial = board.copy()
    trial.push(before.best_move)
    best = judge.evaluate(trial, board.turn)
    return best.mate_in is not None and best.mate_in < 0


def material_text(drop_cp: int, pieces_left_hanging: list[str]) -> str:
    """Say how much is lost, so a real loss isn't mistaken for an even trade. Name a hanging
    piece only if it is worth a minor piece or more; a hanging pawn is rarely what a 250+ cp drop
    is about, so naming it would point at the wrong thing."""
    points = min(9, max(1, round(drop_cp / 100)))
    text = f"⚠ This loses about {points} point{'s' if points != 1 else ''} of material."
    worth = []
    for desc in pieces_left_hanging:  # "knight on f3"
        value = PIECE_VALUE.get(desc.split(" ", 1)[0], 0)
        if value >= 3:
            worth.append((value, desc))
    if worth:
        text += f" Watch your {max(worth)[1]}."
    return text
