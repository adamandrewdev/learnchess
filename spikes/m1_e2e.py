"""M1 end-to-end check against the RUNNING stack, through the web container's /api proxy.
SPENDS MONEY (a few cents: one Sonnet exchange, the rest on Haiku).

    docker compose exec api python spikes/m1_e2e.py

Plays deliberately bad moves (the worst legal move by Stockfish) so the coach is triggered.
"""

from __future__ import annotations

import json
import sys
import urllib.request

import chess

from core.infrastructure.engines.stockfish import Judge

BASE = "http://web:5173/api"


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        # Vite only answers requests addressed to localhost, as a browser's would be.
        headers={"Content-Type": "application/json", "Host": "localhost:5173"},
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        return json.loads(res.read())


def worst_move(judge: Judge, fen: str) -> str:
    board = chess.Board(fen)
    scored = []
    for move in board.legal_moves:
        board.push(move)
        scored.append((judge.evaluate(board, not board.turn).win_prob, move.uci()))
        board.pop()
    return min(scored)[1]


def check(cond: bool, what: str) -> None:
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        sys.exit(1)


def main() -> None:
    with Judge(depth=8) as judge:
        play(judge)


def play(judge: Judge) -> None:
    g = call("POST", "/games", {"color": "white"})
    gid = g["id"]
    print(f"game {gid}")

    # 1. A deliberate blunder triggers "why?"
    g = call("POST", f"/games/{gid}/moves", {"uci": worst_move(judge, g["fen"])})
    check(g["status"] == "awaiting_reason", f"bad move asks why: {g['coach_log'][-1]['question']}")
    check(len(g["moves"]) == 1, "bot waits while the coach asks")

    # 2. Typed answer gets a reply (default model) and a trap is stored
    g = call(
        "POST", f"/games/{gid}/reason",
        {"text": "I wanted to attack with my pawn", "model": "claude-sonnet-5-5"},
    )
    ex = g["coach_log"][-1]
    check(g["status"] == "coach_replied" and bool(ex["reply"]), "coach replied")
    print(f"     [{ex['quality']}] {ex['reply']}")
    check(g["spend"]["month_usd"] > 0, f"spend meter moved: ${g['spend']['month_usd']}")

    # 3. Takeback works
    g = call("POST", f"/games/{gid}/continue", {"retry": True})
    check(g["moves"] == [] and g["fen"] == chess.STARTING_FEN, "retry took the move back")

    # 4. Play the rest of a full game, answering the coach on Haiku, never retrying
    plies = 0
    while g["status"] != "finished" and plies < 200:
        if g["status"] == "player_turn":
            g = call("POST", f"/games/{gid}/moves", {"uci": worst_move(judge, g["fen"])})
            plies += 1
        elif g["status"] == "awaiting_reason":
            g = call(
                "POST", f"/games/{gid}/reason",
                {"text": "no idea honestly", "model": "claude-haiku-5-5"},
            )
        elif g["status"] == "coach_replied":
            g = call("POST", f"/games/{gid}/continue", {"retry": False})
    if g["status"] != "finished":
        g = call("POST", f"/games/{gid}/resign")
    check(g["status"] == "finished", f"game finished: {g['result']} by {g['end_reason']}")
    print(f"     {len(g['moves'])} plies, {len(g['coach_log'])} coach exchanges, "
          f"spend now ${g['spend']['month_usd']}")


if __name__ == "__main__":
    main()
