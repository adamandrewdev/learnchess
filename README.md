# learnchess

Play a human-like bot at your level. When you make a mistake, the coach stops you and asks
**why** you played it, works out the thinking trap behind it, and lets you take it back.
Local only; runs in Docker. Plan and decisions: [PLAN.md](PLAN.md).

## Before the first run

1. Docker Desktop must be running (whale icon in the menu bar).
2. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY`.
   `.env` is git-ignored. A provider whose key is missing just disappears from the model menu.

## Start / stop

| You want to… | Run this (in the repo folder) | What it does |
| --- | --- | --- |
| **Start** | `docker compose up --build -d` | Builds the app image if code changed, starts the three containers in the background (`-d`). First run takes a few minutes. |
| **Open it** | http://localhost:5173 | |
| **Stop** | `docker compose down` | Stops and removes the containers. **Your games are kept** (they live in a Docker volume). |
| See what's running | `docker compose ps` | Lists the containers and whether they're healthy. |
| See the app's logs | `docker compose logs -f api` | Follows the backend's log; Ctrl+C stops following (the app keeps running). |
| Change the spend cap | `SPEND_CAP_USD=2 docker compose up -d` | Restarts the backend with a new monthly cap (default $5). |

**Three containers** (one isolated process each, defined in `docker-compose.yml`):

- `web`: the page you see (React, served by Vite). The only one with a port open to your Mac.
- `api`: the backend (FastAPI), plus Stockfish (judges every move) and Maia-3 (the bot).
- `db`: Postgres, which stores games, coach conversations and the spend log.

## Where your data lives, and how to delete it

Everything is in a Docker **volume** called `learnchess_pgdata`: a folder Docker manages,
which survives `docker compose down`.

- `docker compose down -v` **deletes it permanently** (`-v` = also remove volumes): every game,
  coach reply and the spend history. There is no undo.
- The app image (`learnchess-api:dev`, about 1.8 GB) stays on disk so restarts are quick.
  `docker image rm learnchess-api:dev` removes it; the next start rebuilds it.

## Checks (for development)

`.claude/preflight.sh` runs lint and tests for backend and frontend, inside containers.
