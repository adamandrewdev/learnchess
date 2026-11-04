"""Board facts computed by rules, not by the LLM (PLAN D1, risk H2).

These are the things a 400 player most often misses. Each fact is something
python-chess can prove from the position; the coach may cite them, never invent them.
"""

from __future__ import annotations

import chess

VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


def _describe(board: chess.Board, square: chess.Square) -> str:
    piece = board.piece_at(square)
    return f"{chess.piece_name(piece.piece_type)} on {chess.square_name(square)}"


def hanging_pieces(board: chess.Board, color: chess.Color) -> list[str]:
    """Pieces of `color` that can be taken for profit right now.

    Hanging = attacked and either undefended, or attacked by something cheaper.
    Ignores pins and deeper tactics on purpose: this is the 400-level check, and Stockfish's
    eval covers everything subtler.
    """
    found = []
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        attackers = board.attackers(not color, square)
        if not attackers:
            continue
        cheapest = min(VALUE[board.piece_type_at(a)] for a in attackers)
        defended = bool(board.attackers(color, square))
        if not defended or cheapest < VALUE[piece.piece_type]:
            found.append(_describe(board, square))
    return found


def threats_of_last_move(board: chess.Board) -> list[str]:
    """What the opponent's previous move now attacks (the 'did you check their threat?' fact)."""
    if not board.move_stack:
        return []
    last = board.peek()
    mover = board.piece_at(last.to_square)
    if mover is None:
        return []
    threats = []
    if board.is_check():
        threats.append("check")
    for target in board.attacks(last.to_square):
        victim = board.piece_at(target)
        if victim and victim.color != mover.color and victim.piece_type != chess.KING:
            threats.append(
                f"{chess.piece_name(mover.piece_type)} attacks {_describe(board, target)}"
            )
    return threats


def free_captures(board: chess.Board) -> list[str]:
    """Captures available to the side to move that win material (missed-capture fact)."""
    them = not board.turn
    targets = set(hanging_pieces(board, them))
    out = []
    for move in board.legal_moves:
        if (
            board.is_capture(move)
            and board.piece_at(move.to_square)
            and _describe(board, move.to_square) in targets
        ):
            out.append(board.san(move))
    return out
