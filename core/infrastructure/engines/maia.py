"""Maia-3 as the human-like opponent (PLAN D2).

Maia-3 predicts the move a human of a given rating would play. Two knobs matter:
- `elo`: the rating it imitates (engine accepts 0-5000; how real the low end is, P0-1 measures).
- `temperature`: 0 always plays the single most likely human move, which tends to be
  stronger than an actual human of that rating; >0 samples from the distribution.

Maia-3's UCI wrapper seeds its RNG with a fixed `--seed 42` by default, so without a seed
of our own every fresh engine process plays the same "random" game (found in P0-1).
"""

from __future__ import annotations

import secrets
from typing import Self

import chess
import chess.engine

DEFAULT_CMD = ["maia3-5m", "--device", "cpu", "--no-use-amp", "--local-files-only"]


class Opponent:
    def __init__(
        self,
        elo: int,
        temperature: float = 1.0,
        seed: int | None = None,
        cmd: list[str] | None = None,
    ):
        self.seed = seed if seed is not None else secrets.randbelow(2**31)
        # Loading PyTorch + the checkpoint can exceed python-chess's 10 s default on a busy
        # 4 GB Docker VM (seen in preflight with the full stack running).
        self._engine = chess.engine.SimpleEngine.popen_uci(
            [*(cmd or DEFAULT_CMD), "--seed", str(self.seed)], timeout=60
        )
        self.set_strength(elo, temperature)

    def set_strength(self, elo: int, temperature: float = 1.0) -> None:
        self.elo, self.temperature = elo, temperature
        # Elo conditions the model; SelfElo/OppoElo set the same for both sides.
        self._engine.configure(
            {"Elo": elo, "SelfElo": elo, "OppoElo": elo, "Temperature": str(temperature)}
        )

    def play(self, board: chess.Board) -> chess.Move:
        # Maia-3 needs no search; a node limit of 1 is the documented way to ask for a move.
        return self._engine.play(board, chess.engine.Limit(nodes=1)).move

    def close(self) -> None:
        self._engine.quit()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
