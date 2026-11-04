"""P0-3: does the coach give good feedback, across every usable model? SPENDS MONEY (cents).

Takes 10 mistakes Maia-400 made in P0-1, pairs each with a typical beginner explanation from
p0_3_reasons.json (edit those to sound like you), and asks both models to coach it.
Writes spikes/out/p0_3_report.md for you to read and judge.

Upper bound: 40 calls (10 positions x 4 models), estimated well under $0.50 total.

    docker run --rm --env-file .env -v "$PWD":/app learnchess-api:spike \
        python spikes/p0_3_coach_quality.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import chess
import chess.pgn

from core.infrastructure.analysis.move_review import review_move
from core.infrastructure.coach.coach import Coach
from core.infrastructure.coach.providers import available_models
from core.infrastructure.engines.stockfish import Judge

HERE = Path(__file__).parent
PGN = HERE / "out" / "selfplay_elo400_temp1.0.pgn"
N = 10


def pick_positions(judge: Judge) -> list:
    """First mistake-or-worse per game from the Maia-400 self-play games, skipping move 1-3."""
    picks = []
    with PGN.open() as fh:
        while len(picks) < N and (game := chess.pgn.read_game(fh)):
            board = game.board()
            for move in game.mainline_moves():
                if board.fullmove_number > 3:
                    facts, _ = review_move(judge, board, move)
                    if facts.quality in ("mistake", "blunder"):
                        picks.append(facts)
                        break
                board.push(move)
    return picks


def main() -> None:
    usable, problems = available_models()
    for what, why in problems.items():
        print(f"skipping {what}: {why}", file=sys.stderr)
    if not usable:
        sys.exit("no usable models: put keys in .env and pass --env-file .env")
    model_ids = [m.id for m in usable]
    reasons = json.loads((HERE / "p0_3_reasons.json").read_text())
    with Judge(depth=14) as judge:
        positions = pick_positions(judge)
    if len(positions) < N:
        print(f"only found {len(positions)} positions", file=sys.stderr)

    coaches = {m: Coach(model=m) for m in model_ids}
    totals = {m: {"cost": 0.0, "secs": 0.0, "calls": 0} for m in model_ids}
    lines = ["# P0-3 coach quality\n"]
    for i, facts in enumerate(positions):
        reason = reasons[i % len(reasons)]
        board = chess.Board(facts.fen_before)
        lines += [
            f"## {i + 1}. {facts.move_san} ({facts.quality})",
            (
                f"[position](https://lichess.org/analysis/{facts.fen_before.replace(' ', '_')})"
                f" · {'White' if board.turn else 'Black'} to move · engine preferred "
                f"**{facts.best_move_san}**"
            ),
            f"\n> **Player:** {reason}\n",
            "<details><summary>engine facts given to the coach</summary>\n",
            "```json\n" + json.dumps(facts.__dict__, indent=1) + "\n```\n</details>\n",
        ]
        for model, coach in coaches.items():
            t0 = time.perf_counter()
            result = coach.review(facts, reason)
            secs = time.perf_counter() - t0
            t = totals[model]
            t["cost"] += result.cost_usd
            t["secs"] += secs
            t["calls"] += 1
            v = result
            trap = v.trap.value + (f" ({v.proposed_trap_name})" if v.proposed_trap_name else "")
            lines += [
                (
                    f"**{model}**: trap `{trap}`, retry={v.offer_retry}, "
                    f"{secs:.1f}s, ${result.cost_usd:.4f}\n"
                ),
                f"> {v.reply}\n",
            ]
        print(f"{i + 1}/{len(positions)} done", file=sys.stderr, flush=True)

    lines.append("## Totals\n\n| model | calls | total $ | mean $/call | mean latency |")
    lines.append("| --- | --- | --- | --- | --- |")
    for m, t in totals.items():
        n = t["calls"] or 1
        lines.append(
            f"| {m} | {t['calls']} | ${t['cost']:.4f} | ${t['cost'] / n:.5f} | {t['secs'] / n:.1f}s |"
        )
    out = HERE / "out" / "p0_3_report.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out}")
    print("\n".join(lines[-4:]))


if __name__ == "__main__":
    main()
