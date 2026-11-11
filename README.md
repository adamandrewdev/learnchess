# learnchess

Play a human-like bot at your level. The coach stays quiet during the game, except for a
one-line warning when a move drops material or allows checkmate, which you can take back or
keep. Each game ends with a review, and **Your playstyle** (in the bottom-right panel) shows
your strengths, weaknesses, timing and where games fall apart, built up over every game.
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
| Make the blunder warning pickier | `WARN_MIN_CP_DROP=400 docker compose up -d` | Restarts the backend so it only warns on bigger losses (default 250 = about a knight; 100 = one pawn). |
| Apply database changes after a code update | `docker compose restart api` | The backend updates the database's tables each time it starts. Your games are kept. If the app suddenly errors after new code arrives, this is the first thing to try. |

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

## Back up your games

Run this in the repo folder. It writes your whole history to one file in a `backups/` folder
(git-ignored), named by today's date. It only reads the database, so it's safe any time the app is running.

```sh
mkdir -p backups && docker compose exec -T db pg_dump --clean --if-exists -U learnchess learnchess > backups/learnchess-$(date +%F).sql
```

- `pg_dump` is Postgres's export tool; it runs inside the `db` container and its output lands in
  the file on your Mac (that's what `>` does).
- `--clean --if-exists` makes the file a full replacement: restoring it puts the database back
  exactly as it was at backup time.

**Restoring replaces everything currently in the database** with the backup's contents (games
played since that backup are lost). With the app running:

```sh
docker compose exec -T db psql -q -U learnchess learnchess < backups/learnchess-2026-11-11.sql
```

(Use your file's name.) Then `docker compose restart api` so the backend reconnects cleanly.

## Checks (for development)

`.claude/preflight.sh` runs lint and tests for backend and frontend, inside containers.
