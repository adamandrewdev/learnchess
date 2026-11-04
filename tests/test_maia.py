"""Maia-3 opponent behaviour. Runs only where the engine is installed (the api container)."""

import shutil

import chess
import pytest

pytestmark = pytest.mark.skipif(not shutil.which("maia3-5m"), reason="no maia3")


def opening(seed: int, plies: int = 12) -> list[str]:
    from core.infrastructure.engines.maia import Opponent

    board = chess.Board()
    with Opponent(elo=400, temperature=1.0, seed=seed) as bot:
        while board.ply() < plies and not board.is_game_over():
            board.push(bot.play(board))
    return [m.uci() for m in board.move_stack]


def test_same_seed_replays_the_same_game():
    assert opening(7) == opening(7)


def test_different_seeds_give_different_games():
    # Regression for P0-1: Maia-3 defaults to --seed 42, which made every game identical.
    games = {tuple(opening(seed)) for seed in (1, 2, 3, 4)}
    assert len(games) > 1
