"""Thinking-trap taxonomy (PLAN D5). Seed list; the LLM may propose new ones as `other`.

Descriptions were tightened after P0-3, where models confused the first three traps. Each one
now says what evidence picks it, and PRECEDENCE settles ties.
"""

from enum import StrEnum


class Trap(StrEnum):
    IGNORED_THREAT = "ignored_threat"
    LEFT_PIECE_UNDEFENDED = "left_piece_undefended"
    MISSED_CAPTURE = "missed_capture"
    HOPE_CHESS = "hope_chess"
    NO_PLAN = "no_plan"
    TUNNEL_VISION = "tunnel_vision"
    NONE = "none"  # the reasoning was sound (used when sampling good moves)
    OTHER = "other"  # model proposes a new trap name; quarantined until seen 3+ times


DESCRIPTIONS = {
    Trap.IGNORED_THREAT: (
        "The opponent's LAST move created a threat (listed in threats_they_had) and the "
        "player's move did not deal with it. Requires threats_they_had to contain the thing "
        "that went wrong."
    ),
    Trap.LEFT_PIECE_UNDEFENDED: (
        "The player's OWN move created the problem: it put a piece where it can be taken, or "
        "removed a defender (see pieces_left_hanging / their_best_reply_san). No earlier "
        "threat was involved."
    ),
    Trap.MISSED_CAPTURE: (
        "free_captures_missed was not empty, the player didn't take it, and that is the main "
        "cost of the move."
    ),
    Trap.HOPE_CHESS: (
        "The explanation shows the move only works if the opponent misses an obvious reply "
        "('if they don't notice...')."
    ),
    Trap.NO_PLAN: "The player cannot name a goal ('it looked good', 'no idea', 'just moved').",
    Trap.TUNNEL_VISION: (
        "The player had a clear, specific idea and chased it while missing something else. "
        "Use only when none of the traps above describes the problem better."
    ),
    Trap.NONE: "The move was fine and the reasoning was sound.",
    Trap.OTHER: "None of the above fits; propose a short name.",
}

PRECEDENCE = (
    "If the explanation itself shows hope_chess or no_plan, use that. Otherwise prefer, in "
    "order: ignored_threat, missed_capture, left_piece_undefended, tunnel_vision."
)
