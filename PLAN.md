# learnchess — PLAN

Single source of truth for what's being built and in what order. There is one backlog, and it is §7.

## 1. Status — 4 November 2026

| | |
| --- | --- |
| **Done** | P0, P1 (M1). Adaptive rating D26 (4 Nov 2026), pulled forward from P2. |
| **In flight** | — |
| **Next** | User plays rated games. Rest of P2: trap profile page, post-game summary. |
| **Owed by user** | — |

Runs locally only (`docker compose up` → `http://localhost:<port>`). No deployment, no live URL.

## 2. What we're building

The user: chess.com ~400, plays on the chess.com app, won't write code here, does this for fun.

1. **Play a bot that loses like a human at my level** — around 400 and adapting as I improve, not a weakened engine that blunders at random.
2. **Get stopped when I make a mistake and asked *why* I played it** — the coach works out the thinking trap behind the move, not just the better move.
3. **Fix it on the spot** — take the move back and try again once I understand.
4. **See my recurring thinking traps over time**, so I know what to work on.
5. **Stay under $5/month** in API spend, enforced by the app.

## 3. Settled decisions — don't reopen without a real reason

| # | Decision | Reason / what would reopen it |
| --- | --- | --- |
| D1 | **Stockfish judges positions; the LLM only explains.** The LLM is given engine facts (eval, best line, threats, hanging pieces) and told not to make up variations. | LLMs evaluate positions unreliably. Reopen only if a model can be shown to evaluate positions reliably without an engine. |
| D2 | **Opponent = Maia-3 5M at Elo 400, temperature 1.0, random seed per game.** P0-1 (4 Nov 2026): it blunders 6.6 per 40 moves, leaves pieces hanging on 10.4% of moves and misses 23% of free captures, against ~3.7 / ~4% / ~10% at 800–1500. It scored 0/12 against Stockfish's 1320 floor. No human-error layer needed for P1. **Trap:** Maia-3 defaults to `--seed 42`, which makes every game identical; `Opponent` always passes its own seed (regression test in `tests/test_maia.py`). Rejected: Stockfish `UCI_Elo`/skill level, which blunders robotically. Rejected: original Maia, whose lowest model is 1100. | Maia-3 is open source (AGPL-3.0, fine for personal local use), runs on CPU (5M model), and speaks UCI. Its minimum Elo is **not documented**, so P0-1 measures it. |
| D3 | **Coach timing: after the move, unprompted, with a takeback allowed.** It triggers on every inaccuracy, mistake and blunder, and on roughly 1 in 8 good moves, to check whether the reasoning was real or lucky. | User's choice. The 1-in-8 rate is a setting. |
| D4 | **Free-text answers** to "why did you play that?" | User's choice; it gives the richest signal about traps. |
| D5 | **Thinking-trap taxonomy is hybrid**: a starting list (didn't check the opponent's threat; hope chess; left a piece undefended; moved without a plan; missed a capture; tunnel vision on one piece). The LLM can propose new traps; proposed ones are stored as `proposed` until seen 3+ times. | Keeps the profile consistent from game to game while still finding traps nobody listed. |
| D6 | **Mistake classification by win-probability loss**, not raw centipawns. Thresholds follow common practice (inaccuracy / mistake / blunder) and are tunable. | Centipawn loss is misleading in positions that are already won or lost, which happen a lot at 400. |
| D7 | **Untimed games.** | Coaching conversations shouldn't run down a clock. |
| D8 | **Mac browser only, desktop layout**: board on the left, coach chat on the right. | User's choice. Reopen if phone play is wanted. |
| D9 | **Stack mirrors the user's other repos (gameshop, portfolio, longroadtomaybe):** FastAPI + uvicorn in `backend/` (`main.py`, `routes.py`); a `core/` package installed with `-e .` holding `infrastructure/` (engines, analysis, coach, postgresql); Postgres + SQLAlchemy + Alembic; React 19 + Vite + Tailwind 4 in `frontend/`; ruff + pytest. Compose services: `web`, `api`, `db`. Stockfish and Maia-3 run inside `api`. | The user wants to be able to debug and learn from it later, so a familiar stack beats a minimal one. **Reversed 4 Nov 2026:** first draft chose SQLite in a single container ("no benefit from Postgres for a single user"). That was technically true, but the user's existing knowledge outweighs it. |
| D15 | **LLM calls via `langchain_anthropic` / `langchain_openai`** (structured output, `method="json_schema"` on both), not the raw SDKs and not LangGraph. Cost comes from each response's `usage_metadata`. Both libraries count cached tokens inside `input_tokens` and reasoning tokens inside `output_tokens` (checked in source: langchain-anthropic 1.7.10, langchain-openai 1.7.4). GPT-5.x runs at `reasoning_effort="low"`. | Matches the user's other repos. One call per coach step means no graph is needed; add LangGraph if the coach becomes multi-step. |
| D16 | **Board UI = `react-chessboard`** with `chess.js` for instant legal-move highlighting. The backend (python-chess) re-validates every move and is authoritative. | It's a plain React component, so it fits the stack. Rejected: chessground (GPL, not React-native). |
| D17 | **Langfuse is an optional Compose profile** (`--profile observability`), off by default. | It's the user's existing tool for inspecting prompts, and coaching bugs will be prompt bugs. It's opt-in because it adds four containers. |
| D18 | **REST, not websockets.** A move request returns the bot's reply or a coach question; the coach reply is a second request. | One user, turn-based game, so nothing needs pushing. Revisit only if coach replies need to stream. |
| D10 | **Coach model is switchable in the frontend** between the models in the registry (`core/infrastructure/coach/pricing.py`): Claude Haiku 5.5, Claude Sonnet 5.5, GPT-4.1, GPT-5.1. The menu shows only models whose provider key is set **and** whose provider's free model-list endpoint returns them, checked at startup. **Default: Sonnet 5.5** (user's choice after P0-3, 4 Nov 2026: the most Socratic replies; ~70 games/month within the $5 cap). | User request, 4 Nov 2026. **Revised:** the first draft said Claude only, with Sonnet as a setting. Listing models from the provider means a retired model (GPT-4.1 is reportedly retired 14 Jan 2027) disappears from the menu instead of failing mid-game. **Rejected: older Sonnets** (asked 4 Nov 2026). Sonnet 4/4.5/4.6 cost $3/$15, 50% *more* than Sonnet 5.5; Sonnet 5 costs the same but with 2× the cache-read price; Sonnet 4 is retired and 4.5 deprecated. The cheap option is Haiku 5.5. Reopen only if older models get cheaper. |
| D19 | **The trap label always comes from one fixed model (Haiku 5.5)**, whichever model writes the reply; the two calls run in parallel. | P0-3: the four models gave different traps on 5 of 10 positions (mixing up ignored_threat / left_piece_undefended / tunnel_vision). A profile labelled by whichever model was selected would be noise. Costs ~$0.0004 per coach message. |
| D20 | **The facts include the refutation**: the opponent's best reply and line after the played move, plus a piece list rather than only a FEN string. | P0-3 #5: winning chances fell from 38% to 0% and no model could explain why, because the facts described only the position before the move. (All 9 piece-location claims checked were correct, but a piece list removes the need to read the FEN.) |
| D21 | **Coach stops only on mistakes and blunders, and never while the move still leaves the player ≥85% winning.** Inaccuracies pass silently. Settings: `COACH_MIN_QUALITY`, `COACH_STILL_WINNING`. | Game 7 (user's first real game): stopping on inaccuracies in a 92–98% winning position nagged constantly. Supersedes D3's "every inaccuracy". |
| D22 | **The coach gets the game's last 6 coach exchanges**, with earlier attempts at the same position flagged, and is told to stay consistent and own incomplete hints. | Game 7: with no memory, it hinted at Qxg4, criticised Qxg4, then steered back to it. Replay after the fix: it acknowledged the mixed hints and gave the answer. |
| D23 | **The answer is given when asked for:** automatically after 2 retries of the same position (`REVEAL_AFTER_RETRIES`), when the player asks directly, or via a "Show me the best move" button that also draws an arrow once the move is taken back. | Game 7: "what is the correct move here? everything i try you tell me is wrong", with no way out of the loop. |
| D24 | **Judge clears Stockfish's hash before every evaluation, depth 16** (`JUDGE_DEPTH`). "Free captures" are re-checked by the engine and carry its rating; anything rated a mistake or worse isn't listed. | Measured on game 7: without clearing, the same move's win-prob drop varied 0.02–0.08 over 4 runs (graded anywhere from good to blunder); cleared, it was identical every run. Depth 12→16 moved Be2 from blunder to inaccuracy. Cost: ~0.7–1.0 s analysis per move, 1.7 s click-to-your-turn measured in the browser, missing P0-2's <1 s target at the slow end (target relaxed). |
| D25 | **Answering is optional.** The question offers six neutral quick replies, free text, and skip (take back / keep). Skipping to a take-back on a *good* move first says it was good and asks to confirm. | User feedback 4 Nov 2026: having to type to progress was a blocker; a good move was taken back blind. The neutral question wording (D3) is kept until the player acts. |
| D26 | **Your rating: plain Elo on Maia's scale, start 400, updated only by Rated games.** The bot is set to your current rating for every game (rated or not), so expected score is ~50%. K=48 for the first 10 rated games, then 24. Take-backs shrink *gains* (1→67%, 2→50%, 4→33%); losses count in full. Resign = loss; unfinished rated games don't count. Code: `core/infrastructure/rating.py`. | User's choices 4 Nov 2026: Rated switch per game (quick test games shouldn't count) and take-backs allowed but weighted. Maia-scale, not chess.com: it's self-consistent, which is what keeping the bot challenging needs. Checked first (risk M4): Maia +200 scores 81% at 400→600 and 94% at 800→1000, so the setting really does get stronger there. |
| D11 | **Hard spend cap in the app.** Every call's `usage` is logged and costed; calls are refused once the month's total reaches the cap (default $5). A console spend limit is set as a second layer. | The app's own cap fails safe; the console limit catches bugs in the app's accounting. |
| D12 | **Trap data is persisted from P1**, even though the profile page arrives in P2. | Means the P2 profile starts with history. Costs one table. |
| D13 | **Board look is chess.com-*like*, not a copy.** Neutral charcoal UI, classic brown board, blue accent; green only for "good move". No top bar: game controls, model menu and spend sit in the bottom-right panel. | No borrowed branding. Palette and layout changed 4 Nov 2026 on user feedback ("don't like the green tint"; the bottom-right move list was unused space). |
| D14 | **Coach personas are prompt presets**: patient teacher, blunt, Socratic. P1 ships "patient teacher" only. | User wants selectable personas. They're cheap to add once the coaching loop works. |

**Out of scope (user's decision, 4 Nov 2026):** chess.com game import, phone layout, clocks, any cloud deployment, voice input. Drills from mistakes are not planned yet. The user didn't pick them, but they're a natural P4 if wanted.

## 4. Phases

### P0 — Spikes (de-risk before building UI)
**Entry gate:** this plan agreed. **DONE** (4 Nov 2026).

| ID | Spike | Pass condition |
| --- | --- | --- |
| P0-1 | Maia-3 at its lowest Elo: play ~20 games against Stockfish set to a low strength, and inspect its blunders. | We know Maia-3's real floor. If it plays well above 400, we design the human-error layer: with probability *p*, ignore the opponent's last-move threat or leave a piece hanging, choosing from Maia's own candidate moves. |
| P0-2 | Analysis pipeline: Stockfish eval + threat/hanging-piece extraction (python-chess) per move. | Under 1 s per move on the Mac inside Docker. Facts are correct on 10 hand-checked positions. |
| P0-3 | Coach prompt on 10 real positions with typed "why" answers, on every usable model (Haiku 5.5, Sonnet 5.5, GPT-4.1, GPT-5.1). User reads the outputs side by side. | User picks a default model. Measured cost and latency per call are recorded. **Needs keys in `.env` (user).** Estimated total under $0.50. |

### P1 — MVP: play + coached "why?" loop
**Entry gate:** P0-1, P0-2, P0-3 pass. **OPEN** (4 Nov 2026).
Board; bot at a fixed starting rating of ~400; coach-model menu (D10, `GET /api/models`); move analysis; the coach steps in per D3; free-text reply; takeback/retry; trap classification saved (D12); spend meter and cap (D11); one persona. Started and stopped with `docker compose up` / `down`.

### P2 — Memory and progression
**Entry gate:** P1 milestone M1 met. **CLOSED.**
Trap profile page (recurring traps, trend per week, example positions). Coach refers to past traps in the prompt ("you've done this 4 times this week"). Post-game summary. ~~Adaptive bot rating~~ done early (D26).

### P3 — Personas and tuning
**Entry gate:** M2 met. **CLOSED.**
Persona picker (D14); setting for how often it checks good moves; Sonnet toggle per persona if the budget allows.

## 5. Milestones

| ID | Milestone | Checkable conditions |
| --- | --- | --- |
| M1 | **Playable coach** (met 4 Nov 2026: `spikes/m1_e2e.py` + `spikes/m1_ui.mjs` in a headless browser; spend log recomputed from tokens in SQL and matched) | From a fresh clone, `docker compose up` starts the app (verified by actually opening it, not just green tests). A full game vs the bot completes. A deliberate blunder triggers a "why?" prompt. Typed answer gets a reply that names a trap from D5. Takeback works. The spend meter shows a non-zero, correct-to-the-cent figure against the usage log. Setting the cap to $0.01 blocks the next call with a visible message. |
| M2 | **It remembers me** | Profile page shows traps from ≥3 separate games. A new game's coaching mentions a past trap. Bot rating changed after a run of results. |
| M3 | **Personas** | All three personas selectable; same position gives a clearly different tone in each. |

## 6. Cost model — fetched 4 Nov 2026

Sources: [Anthropic](https://platform.claude.com/docs/en/about-claude/pricing), [OpenAI](https://developers.openai.com/api/docs/pricing) (Standard tier). The code copy is `core/infrastructure/coach/pricing.py`.

**Seven billable meters on two bills.** Anthropic has 4 (input, output, cache write, cache read). OpenAI has 3 (input, cached input, output; no charge for cache writes). Stockfish, Maia and Docker are free. If an eighth line appears on either bill, something is wrong. Don't use: Anthropic `inference_geo` (1.1×), OpenAI data-residency endpoints (+10%), OpenAI Fast/priority or Flex tiers (different prices; the cost code raises an error if it sees them).

| Model | Input | Output | Cache write | Cache read | Est. per coach call* |
| --- | --- | --- | --- | --- | --- |
| Claude Haiku 5.5 | $0.10 | $0.50 | $0.125 | $0.01 | **$0.0004 measured** |
| Claude Sonnet 5.5 | $2.00 | $10.00 | $2.50 | $0.10 | **$0.0065 measured** |
| GPT-4.1 | $2.00 | $8.00 | — | $0.50 | **$0.0022 measured** |
| GPT-5.1 | $1.25 | $10.00 | — | $0.125 | **$0.0027 measured** (reasoning_effort=low) |

Prices are per million tokens; per-call figures are P0-3 means over 10 calls each. At ~10 coach messages per game, plus D19's Haiku label call, $5/month covers ~600 Haiku games, ~70 Sonnet games, ~190 GPT-4.1 games or ~160 GPT-5.1 games. The $5 cap (D11) is one total across both providers.

**Keys are shared with another project.** Each provider console's spend limit and billing then cover both projects together, so the in-app cap (D11) is the only per-app limit.

## 7. Backlog / cross-cutting

| ID | Item | Pinned to | Why there |
| --- | --- | --- | --- |
| X1 | API key handling: `.env` file, git-ignored, read by Compose; never logged. | P0-3 | First phase that calls the API. |
| X2 | Spend cap + usage log (D11). | P1 | Must exist before any regular play. |
| X3 | Postgres on a named Docker volume, so games and traps survive `docker compose down`. Alembic migrations from the first table. | P1 | First persisted data. |
| X4 | Backup = `pg_dump` to a file; document the one command. | P2 | When the trap history becomes worth keeping. |
| X8 | Coach prompt: never mention trap ids in the reply (GPT-4.1 and GPT-5.1 did, P0-3). | P1 | First player-facing replies. |
| X9 | "Coach is thinking…" indicator: replies take 2–6 s (Sonnet up to 10.8 s), measured in P0-3. | P1 | First UI. |
| X7 | `.claude/preflight.sh` running ruff, pytest, frontend lint, matching the other repos. | P1 | First code. |
| X5 | README "how to run it": start, stop, where data lives, what each command changes. Plain English (user's calibration: Docker is Taught). | P1 | M1 condition. |
| X6 | api image is **1.8 GB** (measured 4 Nov 2026: CPU PyTorch + Maia-3 5M checkpoint baked in). Kept on disk on purpose; it's rebuilt from cache. | P1 | First image build. |

## 8. Risks

| ID | Risk | Mitigation |
| --- | --- | --- |
| H1 | Maia-3 at 400 has the right statistics but may not *feel* like a 400 opponent. P0-1 had no real 400 games to compare against. | Judged by the user in M1; optional: same metrics on the user's own chess.com games. Fallback remains a human-error layer. |
| M5 | GPT-4.1 retirement (reported for 14 Jan 2027) and future model churn. | D10: the menu is built from each provider's live model list; prices live in one registry file. |
| M6 | Opening moves are graded harshly: 1.g4 was rated "blunder" in M1 (the win-chance model is very sensitive at ply 0). | Tune D6 thresholds after real games, e.g. raise them in the first ~5 moves. |
| L2 | Docker VM is 4 GB and shared with other projects' containers; engine startup can time out under load. | Maia start timeout raised to 60 s. Fix: stop other stacks while playing, or give Docker Desktop more memory. |
| M4 | **Maia-3 5M stops getting stronger above ~1200:** head-to-head, Maia 1400 scored only 53% vs 1200 (16 games), against 81% (400→600) and 94% (800→1000). | Trigger: user rating ≥1100. Then re-run `spikes/p2_maia_curve.py` with the 23M/79M models; fallback is mixing in weakened Stockfish above 1200. |
| H2 | Coach hallucinates chess (seen once after D20: "Ndb5 moves your knight off d4, so your queen sees g4"; the queen already saw g4) ("your bishop was hanging" when it wasn't). | D1: only engine-derived facts go in; structured output; P0-3 review on known positions. |
| M1 | Haiku's coaching is too shallow or generic. | P0-3 comparison; Sonnet for the "why?" reply only if needed, staying within budget. |
| M2 | Trap classification is inconsistent, so the profile is noise. **Observed in P0-3** (5/10 disagreements across models). | D19 fixed labeller; tighten the descriptions of the three overlapping traps with a rule for telling them apart; re-run P0-3 to check agreement. |
| M3 | Interrupt rate gets annoying. | Thresholds and good-move sampling are settings, tuned after M1. |
| L1 | Large Docker image / slow first build. | X6; reuse the build cache. |

## Ownership

Claude writes the code and runs local checks. The user does git commits/pushes, creates the API key, sets the console spend limit, and runs anything that spends money.
