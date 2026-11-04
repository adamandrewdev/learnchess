"""P2 pre-check (risk M4): does Maia-3 get stronger as its Elo setting goes up?

Head-to-head: Maia(E) vs Maia(E+200), colours alternating, random seeds. If the setting means
anything, the higher one should score clearly above 50% (Elo theory says ~76% for +200).

    docker run --rm -v "$PWD":/app learnchess-api:dev python spikes/p2_maia_curve.py
"""

from __future__ import annotations

import os
import statistics
from concurrent.futures import ProcessPoolExecutor

import chess

from core.infrastructure.engines.maia import Opponent

GAMES = int(os.environ.get("GAMES", "16"))
LEVELS = [400, 800, 1200]
GAP = 200
MAX_PLIES = 200


def play(spec: tuple[int, int]) -> float:
    """Score for the HIGHER-rated Maia in one game."""
    low, game_no = spec
    high_is_white = game_no % 2 == 0
    with Opponent(low, 1.0) as lo, Opponent(low + GAP, 1.0) as hi:
        board = chess.Board()
        while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
            white_to_move = board.turn == chess.WHITE
            mover = hi if white_to_move == high_is_white else lo
            board.push(mover.play(board))
    result = board.result(claim_draw=True)
    if result == "1/2-1/2" or result == "*":
        return 0.5
    white_won = result == "1-0"
    return 1.0 if white_won == high_is_white else 0.0


def main() -> None:
    specs = [(low, i) for low in LEVELS for i in range(GAMES)]
    with ProcessPoolExecutor(max_workers=int(os.environ.get("WORKERS", "3"))) as pool:
        scores = list(pool.map(play, specs))
    for k, low in enumerate(LEVELS):
        s = scores[k * GAMES : (k + 1) * GAMES]
        print(
            f"Maia {low + GAP} vs Maia {low}: higher scores {statistics.mean(s):.0%} "
            f"over {GAMES} games (W/D/L {s.count(1.0)}/{s.count(0.5)}/{s.count(0.0)})"
        )


if __name__ == "__main__":
    main()
