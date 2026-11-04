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


class Judge:
    def __init__(self, path: str | None = None, depth: int = 12, threads: int = 1):
        self.depth = depth
        self._engine = chess.engine.SimpleEngine.popen_uci(
            path or os.environ.get("STOCKFISH_PATH", "stockfish")
        )
        self._engine.configure({"Threads": threads})

    def evaluate(self, board: chess.Board, pov: chess.Color) -> Evaluation:
        # Clear the hash first so the same position always gets the same verdict. Without it,
        # game 7's Be2 scored anywhere from "good" to "blunder" depending on what had been
        # analysed before (measured: win-prob drop 0.02-0.08 over 4 runs at depth 12).
        self._engine.configure({"Clear Hash": None})
        info = self._engine.analyse(board, chess.engine.Limit(depth=self.depth))
        score = info["score"].pov(pov)
        pv = list(info.get("pv", []))
        return Evaluation(
            pov=pov,
            win_prob=score.wdl(model="sf", ply=board.ply()).expectation(),
            score_cp=score.score(),
            mate_in=score.mate(),
            best_move=pv[0] if pv else None,
            pv=pv,
        )

    def close(self) -> None:
        self._engine.quit()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
