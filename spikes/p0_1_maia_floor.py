"""P0-1: how weak does Maia-3 really play, and does it lose like a human?  (+ P0-2 timing)

Runs Maia-3 self-play at several (elo, temperature) settings, plus an anchor match of
Maia-3 vs Stockfish's weakest calibrated setting. Every ply is judged by Stockfish and
checked with the rule-based facts. Writes a JSON summary and PGNs to spikes/out/.

    docker run --rm -v "$PWD":/app learnchess-api:spike python spikes/p0_1_maia_floor.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from core.infrastructure.analysis.classify import Quality, classify
from core.infrastructure.analysis.facts import free_captures, hanging_pieces
from core.infrastructure.engines.maia import Opponent
from core.infrastructure.engines.stockfish import Judge

OUT = Path(__file__).parent / "out"
GAMES = int(os.environ.get("GAMES", "8"))
MAX_PLIES = 160
SELF_PLAY = [(400, 0.0), (400, 1.0), (800, 1.0), (1100, 1.0), (1500, 1.0)]
ANCHOR = (400, 1.0)  # Maia setting played against Stockfish's floor
SF_FLOOR_ELO = 1320  # Stockfish 17's minimum UCI_Elo


def play_game(spec: dict) -> dict:
    """One game. spec: {kind, elo, temp, game_no}."""
    judge = Judge(depth=12)
    maia = Opponent(spec["elo"], spec["temp"])
    weak_sf = None
    maia_color = chess.WHITE if spec["game_no"] % 2 == 0 else chess.BLACK
    if spec["kind"] == "anchor":
        weak_sf = chess.engine.SimpleEngine.popen_uci(os.environ["STOCKFISH_PATH"])
        weak_sf.configure({"UCI_LimitStrength": True, "UCI_Elo": SF_FLOOR_ELO})

    board = chess.Board()
    plies, maia_ms, judge_ms = [], [], []
    before = judge.evaluate(board, chess.WHITE)
    while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
        mover = board.turn
        offered_free = free_captures(board)
        t0 = time.perf_counter()
        if weak_sf is not None and mover != maia_color:
            move = weak_sf.play(board, chess.engine.Limit(time=0.05)).move
        else:
            move = maia.play(board)
            maia_ms.append((time.perf_counter() - t0) * 1000)
        san = board.san(move)
        board.push(move)

        t1 = time.perf_counter()
        after = judge.evaluate(board, chess.WHITE)
        hung = hanging_pieces(board, mover)
        judge_ms.append((time.perf_counter() - t1) * 1000)

        wp_before = before.win_prob if mover == chess.WHITE else 1 - before.win_prob
        wp_after = after.win_prob if mover == chess.WHITE else 1 - after.win_prob
        quality, loss = classify(wp_before, wp_after)
        plies.append(
            {
                "mover_is_maia": weak_sf is None or mover == maia_color,
                "san": san,
                "quality": quality.value,
                "loss": round(loss, 3),
                "left_hanging": bool(hung) and quality is not Quality.GOOD,
                "missed_free_capture": bool(offered_free) and san not in offered_free,
            }
        )
        before = after

    game = chess.pgn.Game.from_board(board)
    label = f"maia{spec['elo']}_t{spec['temp']}"
    if weak_sf is not None:
        sf = f"stockfish{SF_FLOOR_ELO}"
        white, black = (label, sf) if maia_color == chess.WHITE else (sf, label)
        weak_sf.quit()
    else:
        white = black = label
    game.headers.update({"White": white, "Black": black, "Event": spec["kind"]})
    judge.close()
    maia.close()

    result = board.result(claim_draw=True)
    maia_score = None
    if weak_sf is not None and result != "*":
        points = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[result]
        maia_score = points if maia_color == chess.WHITE else 1 - points
    return {
        **spec,
        "result": result,
        "maia_score": maia_score,
        "plies": plies,
        "maia_ms": maia_ms,
        "judge_ms": judge_ms,
        "pgn": str(game),
    }


def summarise(games: list[dict]) -> dict:
    moves = [p for g in games for p in g["plies"] if p["mover_is_maia"]]
    n = len(moves) or 1
    per40 = 40 / n

    def count(q: str) -> int:
        return sum(p["quality"] == q for p in moves)

    scores = [g["maia_score"] for g in games if g["maia_score"] is not None]
    return {
        "games": len(games),
        # Guard against the fixed-seed trap: must be close to `games`, not 1.
        "distinct_games": len({g["pgn"].split("\n\n", 1)[-1] for g in games}),
        "maia_moves": len(moves),
        "blunders_per_40": round(count("blunder") * per40, 2),
        "mistakes_per_40": round(count("mistake") * per40, 2),
        "inaccuracies_per_40": round(count("inaccuracy") * per40, 2),
        "mean_winprob_loss": round(statistics.mean(p["loss"] for p in moves), 3) if moves else 0,
        "pct_moves_left_piece_hanging": round(100 * sum(p["left_hanging"] for p in moves) / n, 1),
        "pct_missed_free_capture": round(
            100 * sum(p["missed_free_capture"] for p in moves) / n, 1
        ),
        "maia_score_vs_sf_floor": round(statistics.mean(scores), 2) if scores else None,
        "results": [g["result"] for g in games],
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    specs = [
        {"kind": "selfplay", "elo": e, "temp": t, "game_no": i}
        for e, t in SELF_PLAY
        for i in range(GAMES)
    ] + [{"kind": "anchor", "elo": ANCHOR[0], "temp": ANCHOR[1], "game_no": i} for i in range(GAMES)]

    workers = int(os.environ.get("WORKERS", "4"))
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        games = []
        for g in pool.map(play_game, specs):
            games.append(g)
            print(f"{len(games)}/{len(specs)} {g['kind']} {g['elo']}/{g['temp']} {g['result']}",
                  file=sys.stderr, flush=True)

    groups: dict[str, list[dict]] = {}
    for g in games:
        groups.setdefault(f"{g['kind']} elo={g['elo']} temp={g['temp']}", []).append(g)

    all_judge = [ms for g in games for ms in g["judge_ms"]]
    all_maia = [ms for g in games for ms in g["maia_ms"]]
    summary = {
        "settings": {name: summarise(gs) for name, gs in groups.items()},
        "timing_ms": {
            "note": f"{workers} games in parallel on the Docker VM, so per-move is pessimistic",
            "judge_depth12_plus_facts_p50": round(statistics.median(all_judge)),
            "judge_depth12_plus_facts_p95": round(sorted(all_judge)[int(0.95 * len(all_judge))]),
            "maia_move_p50": round(statistics.median(all_maia)),
            "maia_move_p95": round(sorted(all_maia)[int(0.95 * len(all_maia))]),
        },
        "wall_clock_s": round(time.perf_counter() - started),
    }
    (OUT / "p0_1_summary.json").write_text(json.dumps(summary, indent=2))
    for name, gs in groups.items():
        safe = name.replace(" ", "_").replace("=", "")
        (OUT / f"{safe}.pgn").write_text("\n\n".join(g["pgn"] for g in gs))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
