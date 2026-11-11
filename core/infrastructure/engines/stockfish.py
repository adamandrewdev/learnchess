"""Stockfish as the judge (PLAN D1): every evaluation fact the coach sees comes from here."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Self

import chess
import chess.engine


@dataclass(frozen=True)
class Evaluation:
    """Engine view of a position, from the perspective of `pov`."""

    pov: chess.Color
    win_prob: float  # expected score in [0, 1] for `pov` (Stockfish WDL model)
    score_cp: int | None  # centipawns for `pov`; None when it's a forced mate
    mate_in: int | None  # moves to mate for `pov` (negative = getting mated)
    best_move: chess.Move | None
    pv: list[chess.Move]  # principal variation starting with best_move
    # Win prob (for `pov`) after the engine's second-best move, when asked for with lines=2.
    # None if not asked for, or if there was only one legal move. Drives "only move" (X11).
    second_win_prob: float | None = None


class Judge:
    def __init__(self, path: str | None = None, depth: int = 12, threads: int = 1):
        self.depth = depth
        self._engine = chess.engine.SimpleEngine.popen_uci(
            path or os.environ.get("STOCKFISH_PATH", "stockfish")
        )
        self._engine.configure({"Threads": threads})

    def evaluate(self, board: chess.Board, pov: chess.Color, lines: int = 1) -> Evaluation:
        """lines=2 also scores the second-best move (MultiPV). Measured on 40 stored positions
        at depth 16 (11 Nov 2026): 0.85 s -> 0.98 s per evaluation."""
        # Clear the hash first so the same position always gets the same verdict. Without it,
        # game 7's Be2 scored anywhere from "good" to "blunder" depending on what had been
        # analysed before (measured: win-prob drop 0.02-0.08 over 4 runs at depth 12).
        self._engine.configure({"Clear Hash": None})
        infos = self._engine.analyse(
            board, chess.engine.Limit(depth=self.depth), multipv=max(1, lines)
        )
        info = infos[0]
        score = info["score"].pov(pov)
        second = None
        if lines > 1 and len(infos) > 1:
            second = infos[1]["score"].pov(pov).wdl(model="sf", ply=board.ply()).expectation()
        pv = list(info.get("pv", []))
        return Evaluation(
            pov=pov,
            win_prob=score.wdl(model="sf", ply=board.ply()).expectation(),
            score_cp=score.score(),
            mate_in=score.mate(),
            best_move=pv[0] if pv else None,
            pv=pv,
            second_win_prob=second,
        )

    def close(self) -> None:
        self._engine.quit()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
