"""Playstyle patterns: strengths and weaknesses as hits / opportunities (PLAN D29).

Everything here is computed from what each move already stores (position before, move, engine
quality, engine facts), so every past game counts without re-running Stockfish. The engine's
verdict (quality) decides hit or miss; the board rules (python-chess) decide whether there was
an opportunity at all. The LLM never decides any of it (D1).

Each pattern has a strength and a weakness reading of the same opportunities, so "you dealt
with 9 of 12 threats" and "you ignored 3 of 12" are one number seen from both sides.

What a bad move is blamed on comes from the engine's punishing reply (their_best_reply_san):
measured over 83 bad moves (6 Nov 2026), it took an already-threatened piece 9 times, took an
unthreatened piece 17 times (the piece just moved, or one whose defender moved), a free capture
was missed 20 times, and 36 were quiet replies. Those 36 are deeper ideas or harsh opening grades
(PLAN M6) that board rules can't name honestly; the player's own answers in the review cover them.

Every move the player made counts, including ones taken back after the blunder warning (D27):
the decision and the thinking behind it were real, and leaving them out made a game whose
blunders the warning caught look clean (user feedback, 6 Nov 2026). Only development, which is
about the position actually reached, uses kept moves alone.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import chess

from core.infrastructure.analysis.facts import VALUE, free_captures, hanging_pieces

OK = ("good", "inaccuracy")  # the engine didn't object much
BAD = ("mistake", "blunder")
WINNING = 0.75  # win chance from which "keep it winning" applies
DEVELOPMENT_MOVES = 10


@dataclass(frozen=True)
class Pattern:
    key: str
    strength: str
    weakness: str


PATTERNS = [
    Pattern("threats", "Dealt with threats to your pieces", "Ignored a threat to a piece"),
    Pattern("captures", "Took free material", "Missed free material"),
    Pattern("safety", "Kept your pieces protected", "Left a piece hanging"),
    Pattern("winning", "Kept a winning position winning", "Let a winning position slip"),
    Pattern("development", "Developed and castled early", "Slow to develop and castle"),
]
BY_KEY = {p.key: p for p in PATTERNS}


@dataclass
class PlayerMove:
    """The stored fields of one kept player move that patterns need."""

    id: int
    game_id: int
    san: str
    uci: str
    fen_before: str
    quality: str | None
    win_prob_before: float | None
    win_prob_after: float | None
    facts: dict | None
    think_ms: int | None = None
    taken_back: bool = False  # e.g. after a D27 warning: still the player's decision


@dataclass
class Moment:
    """A move worth showing in the review's 'what went well'."""

    move_id: int
    san: str
    move_number: int
    text: str
    score: int  # for picking the best few


@dataclass
class MoveTags:
    tags: dict[str, bool] = field(default_factory=dict)  # pattern key -> hit (True) / miss
    moment: Moment | None = None


def _value_of(desc: str) -> int:
    """'knight on f3' -> 3."""
    name = desc.split(" ", 1)[0]
    return next((VALUE[t] for t in VALUE if chess.piece_name(t) == name), 0)


def tag_move(m: PlayerMove) -> MoveTags:
    out = MoveTags()
    if m.quality is None:
        return out
    board = chess.Board(m.fen_before)
    move = chess.Move.from_uci(m.uci)
    me = board.turn
    ok, bad = m.quality in OK, m.quality in BAD
    facts = m.facts or {}
    threatened = hanging_pieces(board, me)  # my pieces that could be taken before I moved
    threatened_squares = {chess.parse_square(d.rsplit(" ", 1)[1]) for d in threatened}
    number = board.fullmove_number
    best: Moment | None = None
    taken = _square_their_reply_takes(board, move, facts) if bad else None

    # Threats: something of mine was en prise. Ignored if the engine's punishing reply takes
    # one of those threatened pieces; otherwise dealt with.
    if threatened:
        if bad and taken in threatened_squares:
            out.tags["threats"] = False
        else:
            out.tags["threats"] = True
            top = max(threatened, key=_value_of)
            if m.quality == "good":
                best = Moment(
                    m.id, m.san, number, f"Dealt with the threat to your {top}", _value_of(top) * 10
                )

    # Free captures: took one (engine agrees), or the engine says a missed one was the cost.
    free = free_captures(board)
    if board.san(move) in free and ok:
        out.tags["captures"] = True
        victim = board.piece_at(move.to_square)
        name = chess.piece_name(victim.piece_type) if victim else "pawn"  # en passant
        value = VALUE[victim.piece_type] if victim else 1
        moment = Moment(
            m.id,
            m.san,
            number,
            f"Took the free {name} on {chess.square_name(move.to_square)}",
            value * 10 + 1,
        )
        if m.quality == "good" and (best is None or moment.score > best.score):
            best = moment
    elif bad and facts.get("free_captures_missed"):
        out.tags["captures"] = False

    # Safety: every move is an opportunity; a miss is a bad move whose punishment takes a piece
    # that wasn't under threat before it (so this move is what exposed it).
    out.tags["safety"] = not (bad and taken is not None and taken not in threatened_squares)

    # Winning: from a clearly winning position, did the move keep it?
    if (m.win_prob_before or 0) >= WINNING:
        if ok:
            out.tags["winning"] = True
            if m.quality == "good" and best is None and (m.win_prob_before or 0) < 0.97:
                best = Moment(m.id, m.san, number, "Kept your winning position under control", 5)
        elif bad:
            out.tags["winning"] = False

    out.moment = best
    return out


def _square_their_reply_takes(
    board: chess.Board, move: chess.Move, facts: dict
) -> chess.Square | None:
    """Square of the piece the engine's best reply captures, or None if it isn't a capture."""
    reply = facts.get("their_best_reply_san")
    if not reply:
        return None
    after = board.copy()
    after.push(move)
    try:
        r = after.parse_san(reply)
    except ValueError:
        return None
    if not after.is_capture(r):
        return None
    if after.is_en_passant(r):
        return r.to_square + (-8 if after.turn == chess.WHITE else 8)
    return r.to_square


def development(moves: list[PlayerMove]) -> bool | None:
    """Castled and moved at least three minor pieces off their starting squares within the
    first DEVELOPMENT_MOVES moves. None if the game was shorter than that."""
    early = [m for m in moves if not m.taken_back][:DEVELOPMENT_MOVES]
    if len(early) < DEVELOPMENT_MOVES:
        return None
    castled = any(m.san.startswith("O-O") for m in early)
    board = chess.Board(early[-1].fen_before)
    board.push_uci(early[-1].uci)
    me = chess.Board(early[0].fen_before).turn
    home = chess.BB_RANK_1 if me == chess.WHITE else chess.BB_RANK_8
    minors = board.pieces(chess.KNIGHT, me) | board.pieces(chess.BISHOP, me)
    developed = len([sq for sq in minors if not chess.BB_SQUARES[sq] & home])
    return castled and developed >= 3


@dataclass
class Counts:
    hits: int = 0
    opportunities: int = 0

    def add(self, hit: bool) -> None:
        self.opportunities += 1
        self.hits += int(hit)

    @property
    def rate(self) -> float | None:
        return self.hits / self.opportunities if self.opportunities else None


def count_patterns(games: dict[int, list[PlayerMove]]) -> dict[str, Counts]:
    """games: game id -> that game's kept player moves, in order."""
    counts = {p.key: Counts() for p in PATTERNS}
    for moves in games.values():
        for m in moves:
            for key, hit in tag_move(m).tags.items():
                counts[key].add(hit)
        dev = development(moves)
        if dev is not None:
            counts["development"].add(dev)
    return counts


def highlights(moves: list[PlayerMove], limit: int = 3) -> list[Moment]:
    kept = [m for m in moves if not m.taken_back]
    found = [t.moment for t in (tag_move(m) for m in kept) if t.moment]
    top = sorted(found, key=lambda x: x.score, reverse=True)[:limit]
    return sorted(top, key=lambda x: x.move_id)


def think_medians(moves: list[PlayerMove], min_n: int = 3) -> dict[str, float | None]:
    """Median seconds of thought for good-ish vs bad moves (D30). None below `min_n` moves."""

    def median(qs):
        xs = [m.think_ms / 1000 for m in moves if m.think_ms is not None and m.quality in qs]
        return round(statistics.median(xs), 1) if len(xs) >= min_n else None

    return {"ok_moves": median(OK), "bad_moves": median(BAD)}
