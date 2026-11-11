"""One-off: add `second_best_win_prob` (X11) to player moves stored before it existed.

Only adds that one key to each move's facts; nothing else changes. Safe to re-run: moves that
already have it are skipped. Takes about 1 s per move (one two-line search at JUDGE_DEPTH).

    docker compose exec api python -m backend.backfill_only_move
"""

from __future__ import annotations

import os
import time

import chess
from sqlalchemy import select

from core.infrastructure.engines.stockfish import Judge
from core.infrastructure.postgresql.db import make_sessionmaker
from core.infrastructure.postgresql.models import Move


def main() -> None:
    sessionmaker = make_sessionmaker()
    with sessionmaker() as session, Judge(depth=int(os.environ.get("JUDGE_DEPTH", "16"))) as judge:
        todo = [
            m
            for m in session.scalars(select(Move).where(Move.by == "player").order_by(Move.id))
            if m.facts is not None and "second_best_win_prob" not in m.facts
        ]
        print(f"{len(todo)} moves to backfill", flush=True)
        start = time.perf_counter()
        for i, m in enumerate(todo, 1):
            board = chess.Board(m.fen_before)
            ev = judge.evaluate(board, board.turn, lines=2)
            second = None if ev.second_win_prob is None else round(ev.second_win_prob, 3)
            m.facts = {**m.facts, "second_best_win_prob": second}  # new dict: JSON isn't tracked
            if i % 25 == 0 or i == len(todo):
                session.commit()
                print(f"{i}/{len(todo)} ({time.perf_counter() - start:.0f} s)", flush=True)
        session.commit()


if __name__ == "__main__":
    main()
