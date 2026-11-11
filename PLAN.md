# learnchess — PLAN

Single source of truth for what's being built and in what order. There is one backlog, and it is §7.

## 1. Status — 11 November 2026

| | |
| --- | --- |
| **Done** | P0, P1 (M1), P2a (M2), P2b (M3, measured 11 Nov 2026 from games 51–55: see §6). Adaptive rating D26. P2a + P2b committed (`4e5f5c2`). |
| **In flight** | P2c built 11 Nov 2026: profile page, only-move pattern (X11), backup command (X4). Board/piece themes (`frontend/src/themes.js`) also uncommitted; D13 still holds (no green boards). |
| **Next** | User looks at the profile and says what reads wrong. Then P2d: session focus (D32). |
| **Owed by user** | Commit the theme work and P2c. Say how the review and the profile read. |

Runs locally only (`docker compose up` → `http://localhost:<port>`). No deployment, no live URL.

## 2. What we're building

The user: chess.com ~400, plays on the chess.com app, won't write code here, does this for fun. Learns best by **doubling down on what they already do well while bringing up their weak areas**.

1. **Play a bot that loses like a human at my level**: around 400 and adapting as I improve, not a weakened engine that blunders at random.
2. **Play without interruption**: one small warning only when I'm about to make an obvious blunder, with the option to take it back.
3. **A review at the end of each game**: what went well, my few costliest mistakes (asked *why* about those only), and my thinking patterns compared with my history, good and bad.
4. **A playstyle profile that builds over time**: strengths and weaknesses with trends, how long I think before different kinds of move, and where my games fall apart.
5. **A focus each session**: one strength to keep, one weakness to work on, scored in the review.
6. **Stay under $5/month** in API spend, enforced by the app.

## 3. Settled decisions — don't reopen without a real reason

| # | Decision | Reason / what would reopen it |
| --- | --- | --- |
| D1 | **Stockfish judges positions; the LLM only explains.** The LLM is given engine facts (eval, best line, threats, hanging pieces) and told not to make up variations. Extends to the profile: **all counts, rates and timings are computed in SQL/Python; the LLM only writes them up.** | LLMs evaluate positions unreliably. Reopen only if a model can be shown to evaluate positions reliably without an engine. |
| D2 | **Opponent = Maia-3 5M at Elo 400, temperature 1.0, random seed per game.** P0-1 (4 Nov 2026): it blunders 6.6 per 40 moves, leaves pieces hanging on 10.4% of moves and misses 23% of free captures, against ~3.7 / ~4% / ~10% at 800–1500. It scored 0/12 against Stockfish's 1320 floor. No human-error layer needed for P1. **Trap:** Maia-3 defaults to `--seed 42`, which makes every game identical; `Opponent` always passes its own seed (regression test in `tests/test_maia.py`). Rejected: Stockfish `UCI_Elo`/skill level, which blunders robotically. Rejected: original Maia, whose lowest model is 1100. | Maia-3 is open source (AGPL-3.0, fine for personal local use), runs on CPU (5M model), and speaks UCI. Its minimum Elo is **not documented**, so P0-1 measures it. |
| D3 | ~~Coach steps in after every inaccuracy/mistake/blunder and ~1 in 8 good moves.~~ **Superseded by D27/D28** (6 Nov 2026). | User: "the coach is quite invasive, I find myself skipping feedback a lot." |
| D4 | **Free-text answers** to "why did you play that?", now asked in the review only (D28). | User's choice; it gives the richest signal about traps. |
| D5 | **Thinking-trap taxonomy is hybrid**: a starting list (didn't check the opponent's threat; hope chess; left a piece undefended; moved without a plan; missed a capture; tunnel vision on one piece). The LLM can propose new traps; proposed ones are stored as `proposed` until seen 3+ times. Strengths get a matching list (D29). | Keeps the profile consistent from game to game while still finding traps nobody listed. |
| D6 | **Mistake classification by win-probability loss**, not raw centipawns. Thresholds follow common practice (inaccuracy / mistake / blunder) and are tunable. Used for ranking the review's mistakes and the profile; **not** for the in-game warning (D27). | Centipawn loss is misleading in positions that are already won or lost, which happen a lot at 400. |
| D7 | **Untimed games.** No clock is shown. Think time is still *recorded* (D30). | No pressure while playing; timing is for the profile, not the game. |
| D8 | **Mac browser only, desktop layout**: board on the left, panel on the right. During play the panel holds the move list and the one-line warning (D27); the review (D28) is its own screen after the game. | User's choice. Reopen if phone play is wanted. |
| D9 | **Stack mirrors the user's other repos (gameshop, portfolio, longroadtomaybe):** FastAPI + uvicorn in `backend/` (`main.py`, `routes.py`); a `core/` package installed with `-e .` holding `infrastructure/` (engines, analysis, coach, postgresql); Postgres + SQLAlchemy + Alembic; React 19 + Vite + Tailwind 4 in `frontend/`; ruff + pytest. Compose services: `web`, `api`, `db`. Stockfish and Maia-3 run inside `api`. | The user wants to be able to debug and learn from it later, so a familiar stack beats a minimal one. **Reversed 4 Nov 2026:** first draft chose SQLite in a single container ("no benefit from Postgres for a single user"). That was technically true, but the user's existing knowledge outweighs it. |
| D15 | **LLM calls via `langchain_anthropic` / `langchain_openai`** (structured output, `method="json_schema"` on both), not the raw SDKs and not LangGraph. Cost comes from each response's `usage_metadata`. Both libraries count cached tokens inside `input_tokens` and reasoning tokens inside `output_tokens` (checked in source: langchain-anthropic 1.7.10, langchain-openai 1.7.4). GPT-5.x runs at `reasoning_effort="low"`. | Matches the user's other repos. One call per coach step means no graph is needed; add LangGraph if the coach becomes multi-step. |
| D16 | **Board UI = `react-chessboard`** with `chess.js` for instant legal-move highlighting. The backend (python-chess) re-validates every move and is authoritative. | It's a plain React component, so it fits the stack. Rejected: chessground (GPL, not React-native). |
| D17 | **Langfuse is an optional Compose profile** (`--profile observability`), off by default. | It's the user's existing tool for inspecting prompts, and coaching bugs will be prompt bugs. It's opt-in because it adds four containers. |
| D18 | **REST, not websockets.** A move request returns the bot's reply (and a warning if D27 fires); the review is fetched once the game ends. | One user, turn-based game, so nothing needs pushing. Revisit only if review text needs to stream. |
| D10 | **Coach model is switchable in the frontend** between the models in the registry (`core/infrastructure/coach/pricing.py`): Claude Haiku 5.5, Claude Sonnet 5.5, GPT-4.1, GPT-5.1. The menu shows only models whose provider key is set **and** whose provider's free model-list endpoint returns them, checked at startup. **Default: Sonnet 5.5** (user's choice after P0-3, 4 Nov 2026: the most Socratic replies). | User request, 4 Nov 2026. Listing models from the provider means a retired model (GPT-4.1 is reportedly retired 14 Jan 2027) disappears from the menu instead of failing mid-game. **Rejected: older Sonnets** (asked 4 Nov 2026). Sonnet 4/4.5/4.6 cost $3/$15, 50% *more* than Sonnet 5.5; Sonnet 5 costs the same but with 2× the cache-read price; Sonnet 4 is retired and 4.5 deprecated. The cheap option is Haiku 5.5. Reopen only if older models get cheaper. |
| D19 | **The trap label always comes from one fixed model (Haiku 5.5)**, whichever model writes the reply; the two calls run in parallel. | P0-3: the four models gave different traps on 5 of 10 positions (mixing up ignored_threat / left_piece_undefended / tunnel_vision). A profile labelled by whichever model was selected would be noise. Costs ~$0.0004 per coach message. |
| D20 | **The facts include the refutation**: the opponent's best reply and line after the played move, plus a piece list rather than only a FEN string. | P0-3 #5: winning chances fell from 38% to 0% and no model could explain why, because the facts described only the position before the move. |
| D21 | ~~Coach stops only on mistakes/blunders, never while ≥85% winning.~~ **Superseded by D27.** Its "still winning" guard carries over to the warning. | Game 7: stopping on inaccuracies in a 92–98% winning position nagged constantly. |
| D22 | **Within a review, the coach sees the earlier exchanges about that game** and is told to stay consistent and own incomplete hints. | Game 7: with no memory, it hinted at Qxg4, criticised Qxg4, then steered back to it. |
| D23 | **The answer is given when asked for**, in the review's mistake questions: when the player asks directly, or via "Show me the best move" (board arrow). | Game 7: "what is the correct move here? everything i try you tell me is wrong". |
| D24 | **Judge clears Stockfish's hash before every evaluation, depth 16** (`JUDGE_DEPTH`). "Free captures" are re-checked by the engine and carry its rating; anything rated a mistake or worse isn't listed. | Measured on game 7: without clearing, the same move's win-prob drop varied 0.02–0.08 over 4 runs; cleared, it was identical every run. Cost: ~0.7–1.0 s analysis per move, 1.7 s click-to-your-turn measured in the browser. |
| D25 | ~~Answering mid-game is optional (quick replies / free text / skip).~~ **Superseded by D28**: the same quick replies, free text and skip move to the review's mistake questions. | User feedback 4 Nov 2026: having to type to progress was a blocker. |
| D26 | **Your rating: plain Elo on Maia's scale, start 400, updated only by Rated games.** The bot is set to your current rating for every game (rated or not), so expected score is ~50%. K=48 for the first 10 rated games, then 24. Take-backs (including after a D27 warning) shrink *gains* (1→67%, 2→50%, 4→33%); losses count in full. Resign = loss; unfinished rated games don't count. Code: `core/infrastructure/rating.py`. | User's choices 4 Nov 2026. Maia-scale, not chess.com: it's self-consistent, which is what keeping the bot challenging needs. Checked first (risk M4): Maia +200 scores 81% at 400→600 and 94% at 800→1000. |
| D27 | **Quiet play: the only in-game interruption is a blunder warning, and it comes from the engine, not the LLM.** It fires when the played move (a) newly allows a forced mate in ≤3, or (b) drops the eval by ≥250 centipawns (roughly a minor piece) **from the accepted position**: the lower of best play now and where the player's previous move left them (`moves.eval_cp_after`). And never while the move still leaves the player ≥85% winning. Shown as one line beside the board, saying how much is lost ("⚠ This loses about 3 points of material. Watch your knight on f3."; the piece is named only if a minor piece or more is hanging), with **Take back** / **Keep**. **Revised 6 Nov 2026 (game 47):** measured against best play only, one unresolved problem (6.Bd3 blocked the queen's defence of d4; ...exd4 and trades won a piece; the bot never took it) was warned about on 6 consecutive moves, and the unquantified "loses material" read as flagging ordinary trades. Replayed under the new rule: 9 warnings → 2 (Bd3, and a real mate). Missing the opponent's blunder is not warned about; that belongs to the review. **Also (game 50):** no mate warning when the engine's best move allows mate too (`mate_unavoidable`): in check with three legal king moves, all mated, each was warned about because the search before the move hadn't seen the mate yet. One extra search, only on would-be mate warnings. No chat, no question. Settings: `WARN_MATE_DEPTH`, `WARN_MIN_CP_DROP`, `WARN_STILL_WINNING`. Each warning and its outcome is stored on the move. | User feedback 6 Nov 2026: "subtle warnings only when I'm making an obvious blunder". Centipawns, not win-prob (D6), because "obvious" means a concrete material/mate swing; win-prob drops fire on subtle moves in level positions. Engine-only means instant and free. Thresholds are starting values; tune from the stored warnings (risk R1). |
| D28 | **End-of-game review**, one screen, shown when a game ends and reopenable from the profile. Three parts: **What went well**: 2–3 moments from D29 strengths, each a steppable board. **Biggest mistakes**: the 3 costliest *kept* moves by win-prob loss (D6), each showing the refutation (D20) and better move, with "why did you play that?" (quick replies / free text / skip; D4, D22, D23, trap label per D19). **Thinking patterns**: this game against history (D29 rates, D30 timing), e.g. "you missed their threat 3 times again; 6 of your last 8 games". **One LLM-written summary per game** from computed numbers (D1); plus up to 3 reply+label pairs if answered. | User feedback 6 Nov 2026: "feedback should come at the end of each game… most importantly a review of my ongoing patterns of thinking, both good and bad". Three mistakes, not all of them, so the review stays readable and answerable. **Revised 6 Nov 2026 (user feedback: "no blunders" was hollow when the warning had caught some):** every move the player made counts, including ones taken back after a D27 warning, in the mistakes, patterns and timing; only development uses kept moves. The review says how many blunders the warning caught (this game, and per game over history since P2a), and the summary may not call a game mistake-free if any were. The same move from the same position counts once; warned, taken back and replayed is shown as "played anyway after a warning". |
| D29 | **Strengths and weaknesses are both measured as rates: hits ÷ opportunities, detected by the engine where possible.** Strengths (starting list): handled the opponent's threat; took free material; found the only good move (needs a second engine line, `multipv=2`); kept a winning position winning; developed and castled early. Engine-measurable weaknesses use the same opportunities inverted (ignored threat, missed capture, left a piece undefended). LLM-only traps (hope chess, no plan, tunnel vision) are counts from review answers. | "Double down on what I do well" needs strengths to exist; today only faults are labelled. Rates make "you handled threats on 9 of 12 moves" possible and comparable across games of different length. |
| D30 | **Think time per move, measured in the browser**: from the bot's move appearing to the player's move being sent, excluding time the tab was hidden (Page Visibility API), capped at 5 min, stored as `think_ms` on the move. Not shown during play. Summarised with medians, split by move quality, game phase, and whether the opponent had just made a threat. | User: "this includes move timings". At ~400 the rushed blunder is a common pattern and only timing data can show it. Medians and the cap stop a walk-away from distorting it. |
| D31 | **Games flagged `exclude_from_profile` are skipped by every playstyle statistic** (profile, review patterns, session focus); their rows are kept. Game 50 (deliberately random, 6 Nov 2026) is flagged at the user's request. **Profile page**: strengths and weaknesses with rate and trend (last 10 games vs the 10 before); timing patterns (D30); breakdowns by phase (opening = first 10 moves each; endgame = queens off or ≤13 points of non-pawn material; else middlegame), colour, and eval state (ahead ≥65% win chance / level / behind ≤35%); rating graph (D26); game list linking to each review. | User: "tracking games over time and building up a strong profile of my playstyle". |
| D32 | **Session focus: one strength to keep, one weakness to work on.** Picked automatically: the weakness with the worst rate over the last 10 games (minimum 10 opportunities), the strength with the best. Shown as one line before a game; scored in that game's review. The weakness rotates once its rate has improved over 5 games; the player can override either. | User: "doubling down on what I do well whilst simultaneously bringing up my weak areas". |
| D11 | **Hard spend cap in the app.** Every call's `usage` is logged and costed; calls are refused once the month's total reaches the cap (default $5). A console spend limit is set as a second layer. | The app's own cap fails safe; the console limit catches bugs in the app's accounting. |
| D12 | **Trap data is persisted from P1**, even though the profile page arrives in P2. Games played before P2a have no think time and use the old coach flow; their traps still count. | Means the P2 profile starts with history. |
| D13 | **Board look is chess.com-*like*, not a copy.** Neutral charcoal UI, classic brown board, blue accent; green only for "good move"; amber for the D27 warning. No top bar: game controls, model menu and spend sit in the bottom-right panel. | No borrowed branding. Palette and layout changed 4 Nov 2026 on user feedback. |
| D14 | **Coach personas are prompt presets**: patient teacher, blunt, Socratic. They now set the voice of the review (D28). P1 ships "patient teacher" only. | User wants selectable personas. They're cheap to add once the review works. |

**Out of scope (user's decision, 4 Nov 2026):** chess.com game import, phone layout, clocks, any cloud deployment, voice input.

**Accepted trade-off (6 Nov 2026):** fewer "why?" questions (≤3 per game instead of ~10) means LLM-only traps (hope chess, no plan) build up in the profile more slowly. Engine-detected traps are unaffected (D29).

## 4. Phases

### P0 — Spikes (de-risk before building UI)
**DONE** (4 Nov 2026). Maia-3 floor measured (D2); analysis pipeline under target (D24); coach model chosen (D10).

### P1 — MVP: play + coached "why?" loop
**DONE** (4 Nov 2026, M1). Board, bot, coach-model menu, analysis, takeback, trap storage, spend cap, one persona.

### P2 — Quiet play, review, profile
**Entry gate:** M1 met. **OPEN** (6 Nov 2026). Built in this order; each step is usable on its own.

| Step | Scope | Why this order |
| --- | --- | --- |
| P2a | **Built 6 Nov 2026.** Quiet play: mid-game coach stops and good-move checks removed; D27 warning (`core/infrastructure/analysis/warning.py`); D30 `think_ms` recorded from the first game. Migrations `a3c1e9d27f30` (`moves.think_ms`, `moves.warning`, `moves.warning_outcome`) and `b7d2f4a8c911` (`moves.eval_cp_after`). | Fixes the irritation immediately, and timing data starts accumulating before anything displays it. |
| P2b | **Built 6 Nov 2026.** End-of-game review (D28): `backend/review_service.py`, `core/infrastructure/analysis/patterns.py` (D29 detectors, pulled forward from P2c because "what went well" needs them), `frontend/src/components/ReviewPanel.jsx`. Review exchanges reuse `coach_exchanges` (`reason_asked = "review"`); the summary is cached in `game_reviews` with the numbers it was written from (R3). Summary is written automatically once every question is answered or skipped, or on a button. | Restores the feedback, in the place the user asked for it. |
| | *Detector calibration (6 Nov 2026):* of 83 bad moves in history, the engine's punishing reply took an already-threatened piece 9×, took an unthreatened piece 17×, a free capture was missed 20×, and 36 were quiet replies (deeper ideas or harsh opening grades, M6). Bad moves are blamed by that reply; the quiet ones stay unlabelled by the engine and are covered by the player's answers. | |
| P2c | **Built 11 Nov 2026.** `backend/profile_service.py` (`GET /api/profile`), `frontend/src/components/ProfilePage.jsx` ("Your playstyle" in the controls panel). Only-move (X11) added to D29. Past games open on their review; a reopened review never writes its summary automatically (browsing must not spend). No migration: the second engine line is a new key in `moves.facts`, backfilled for history by `backend/backfill_only_move.py`. | Needs a few games of P2a timing data to be worth looking at. |
| | *Choices made in the build:* endgame = queens off, or **each side** ≤13 points of non-pawn material (D31 didn't say which). The headline names the strongest and weakest pattern by raw rate among those with ≥10 chances in the last 10 games; rates aren't strictly comparable across patterns (safety counts every move), so revisit if the headline is always the same pair. "Where games fall apart" = share of moves rated mistake/blunder; the opening share runs high partly because of M6. | |
| P2d | Session focus (D32), scored in the review. | Needs P2c's rates to choose from. |

### P3 — Personas and tuning
**Entry gate:** M4 met. **CLOSED.**
Persona picker (D14); tune D27 thresholds from stored warnings.

### P4 — Practice from your own games
**CLOSED.** Not committed. Positions from the player's games where they made their focus mistake (to fix) and where they played well (to reinforce).

## 5. Milestones

| ID | Milestone | Checkable conditions |
| --- | --- | --- |
| M1 | **Playable coach** (met 4 Nov 2026) | From a fresh clone, `docker compose up` starts the app; full game completes; blunder → "why?"; trap named; takeback; spend meter correct; $0.01 cap blocks. |
| M2 | **Quiet play** (P2a) | A full game with no coach interruptions. A deliberate piece hang triggers the one-line warning; take back and keep both work; an inaccuracy in a level position does **not** warn; hanging a pawn while ≥85% winning does **not** warn. Every player move in that game has a plausible `think_ms`; a move made after switching tabs for 30 s excludes those 30 s. Verified by opening the app, not only by tests. |
| M3 | **It reviews me** (P2b) (met 11 Nov 2026) | Game end opens the review with all three parts. Exactly ≤3 mistakes listed, all kept moves. Answering one gets a reply and a trap label; skipping works. Spend log shows one summary call per game. Measured per-game cost recorded in §6. |
| M4 | **It knows me** (P2c, P2d) | Profile shows strength and weakness rates with trends from ≥5 games, a timing split by move quality, the phase/colour/eval breakdowns, and the rating graph. A session focus is shown before a game and scored in its review. |
| M5 | **Personas** (P3) | All three personas selectable; same review in each gives a clearly different tone. |

## 6. Cost model — fetched 4 Nov 2026

Sources: [Anthropic](https://platform.claude.com/docs/en/about-claude/pricing), [OpenAI](https://developers.openai.com/api/docs/pricing) (Standard tier). The code copy is `core/infrastructure/coach/pricing.py`.

**Seven billable meters on two bills.** Anthropic has 4 (input, output, cache write, cache read). OpenAI has 3 (input, cached input, output; no charge for cache writes). Stockfish, Maia and Docker are free. If an eighth line appears on either bill, something is wrong. Don't use: Anthropic `inference_geo` (1.1×), OpenAI data-residency endpoints (+10%), OpenAI Fast/priority or Flex tiers (different prices; the cost code raises an error if it sees them).

| Model | Input | Output | Cache write | Cache read | Per coach call* |
| --- | --- | --- | --- | --- | --- |
| Claude Haiku 5.5 | $0.10 | $0.50 | $0.125 | $0.01 | **$0.0004 measured** |
| Claude Sonnet 5.5 | $2.00 | $10.00 | $2.50 | $0.10 | **$0.0065 measured** |
| GPT-4.1 | $2.00 | $8.00 | — | $0.50 | **$0.0022 measured** |
| GPT-5.1 | $1.25 | $10.00 | — | $0.125 | **$0.0027 measured** (reasoning_effort=low) |

Prices are per million tokens; per-call figures are P0-3 means over 10 calls each. The $5 cap (D11) is one total across both providers.

**Per game, after P2 (measured 11 Nov 2026, games 51–55):** the Sonnet summary averages **$0.015** (4 calls; Haiku: $0.0012). Each answered question costs ~$0.010 on Sonnet (reply) + $0.0004 (D19 label). Games 52–53 (2 answered each, Sonnet) cost **$0.035–0.039** all in, against the $0.04 estimate. At that rate $5 covers ~130 games a month. The D27 warning costs nothing.

**Keys are shared with another project.** Each provider console's spend limit and billing then cover both projects together, so the in-app cap (D11) is the only per-app limit.

## 7. Backlog / cross-cutting

| ID | Item | Pinned to | Why there |
| --- | --- | --- | --- |
| X4 | **Done 11 Nov 2026.** Backup/restore commands in the README; tested by restoring a dump into a throwaway Postgres (row counts matched). | P2c | The profile makes history worth keeping. |
| X10 | **Done in P2a** (6 Nov 2026): the mid-game coach path is gone from the game service, routes and panel, with its settings. Kept for P2b: `core/infrastructure/coach/` (prompt, labeller, `explain_best`), the `coach_exchanges` table, and the old flow in git history (`e84e793`) for the reveal/retry logic. Games left waiting on an old question are not resumed; the page starts a new one. | — | The review is a different flow (questions about past moves, not a pending one), so it reuses the coach, not the state machine. |
| X11 | **Done 11 Nov 2026, per move.** Measured on 40 stored positions at depth 16: 0.85 s → 0.98 s per evaluation, added to one search per move (~+0.13 s on 1.7 s). Only move = the second-best move is ≥0.10 win-prob worse (the D6 mistake threshold); found = played move rated "good". Recaptures count. | P2c | First use of a second line. |
| X8 | Coach prompt: never mention trap ids in the reply (GPT-4.1 and GPT-5.1 did, P0-3). | Done (P1) | Applies to the review prompt too. |
| X5 | README "how to run it": start, stop, where data lives, what each command changes. Plain English (user's calibration: Docker is Taught). Update when P2 adds migrations. | P2a | New migration = new run step to explain. |
| X6 | api image is **1.8 GB** (measured 4 Nov 2026: CPU PyTorch + Maia-3 5M checkpoint baked in). Kept on disk on purpose; it's rebuilt from cache. | — | |

## 8. Risks

| ID | Risk | Mitigation |
| --- | --- | --- |
| R1 | **D27 thresholds misfire**: warnings on non-obvious moves (annoying again) or silence on a hung queen. | Every warning and its outcome is stored; review after ~10 games and tune the three settings. M2 has explicit should-warn / shouldn't-warn checks. |
| L3 | **Docker VM memory is full** with this stack, gameshop's Langfuse stack (~1.8 GB, ClickHouse 926 MB) and a test copy: Postgres in the test copy was OOM-killed on 6 Nov 2026. | Browser checks run against one stack at a time; stop gameshop's stack when testing here, or raise Docker Desktop's memory. |
| R2 | **Think time is noisy**: stepping away without switching tabs, or thinking during the bot's move. Also: in the P2a headless check, a starved browser (three stacks in the 4 GB Docker VM) added 0.3–5 s of click lag to recorded times; the hidden-tab exclusion and the start point checked out (326 ms floor; 3 s hidden excluded). | Medians, 5-minute cap (D30). Timing patterns are only shown once a split has ≥20 moves. Checked 11 Nov 2026 before P2c: 287 timed moves over 11 games, median 6.1 s, min 0.9 s, max 115 s, none capped. |
| R3 | Review summary invents patterns not in the numbers. | D1: the prompt gets computed rates only and is told to cite them; structured output with the numbers it used, checked against the DB in tests. |
| H1 | Maia-3 at 400 has the right statistics but may not *feel* like a 400 opponent. | Judged by the user over real games. Fallback remains a human-error layer. |
| M5 | GPT-4.1 retirement (reported for 14 Jan 2027) and future model churn. | D10: the menu is built from each provider's live model list; prices live in one registry file. |
| M6 | Opening moves are graded harshly: 1.g4 was rated "blunder" in M1. Now affects which mistakes the review lists. | Tune D6 thresholds after real games, e.g. raise them in the first ~5 moves. |
| L2 | Docker VM is 4 GB and shared with other projects' containers; engine startup can time out under load. | Maia start timeout raised to 60 s. Fix: stop other stacks while playing, or give Docker Desktop more memory. |
| M4 | **Maia-3 5M stops getting stronger above ~1200.** | Trigger: user rating ≥1100. Then re-run `spikes/p2_maia_curve.py` with the 23M/79M models; fallback is mixing in weakened Stockfish above 1200. |
| H2 | Coach hallucinates chess. | D1: only engine-derived facts go in; structured output. |
| M2 | Trap classification is inconsistent, so the profile is noise. **Observed in P0-3.** | D19 fixed labeller; D29 moves the engine-detectable traps off the LLM entirely. |

## Ownership

Claude writes the code and runs local checks. The user does git commits/pushes, creates the API key, sets the console spend limit, and runs anything that spends money.
