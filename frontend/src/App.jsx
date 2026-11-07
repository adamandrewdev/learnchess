import { useEffect, useRef, useState } from "react";
import { Chess } from "chess.js";
import { api } from "./services/api.js";
import Board from "./components/Board.jsx";
import CoachPanel from "./components/CoachPanel.jsx";
import ReviewPanel from "./components/ReviewPanel.jsx";
import Controls from "./components/Controls.jsx";

const MODEL_KEY = "learnchess.model";
const GAME_KEY = "learnchess.gameId";
const RATED_KEY = "learnchess.rated";

// Positions for stepping through a review moment: the position before, then after each move.
function framesFor(fenBefore, line) {
  const chess = new Chess(fenBefore);
  const frames = [{ fen: fenBefore, lastMove: null }];
  for (const uci of line) {
    try {
      chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    } catch {
      break;
    }
    frames.push({ fen: chess.fen(), lastMove: uci });
  }
  return frames;
}

function remembered(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode etc. */
  }
}

export default function App() {
  const [models, setModels] = useState(null);
  const [model, setModel] = useState(null);
  const [game, setGame] = useState(null);
  const [busy, setBusy] = useState(null); // null | "bot"
  const [error, setError] = useState(null);
  const [rated, setRated] = useState(() => remembered(RATED_KEY) === "true");
  const started = useRef(false);
  const [reviewState, setReview] = useState(null);
  const [reviewBusy, setReviewBusy] = useState(null); // move id | "reveal-<id>" | "summary"
  const [focusState, setFocus] = useState(null); // { gameId, id, label, fenBefore, line, arrow }
  const [frame, setFrame] = useState(0);
  const finishedId = game?.status === "finished" ? game.id : null;
  // Both belong to one game; a new game simply stops matching them.
  const review = reviewState?.game_id === finishedId ? reviewState : null;
  const focus = focusState?.gameId === finishedId ? focusState : null;
  // Think time (PLAN D30): from the board becoming yours to your move, minus time the tab
  // was hidden. Not shown anywhere during play.
  const turnStart = useRef(null);
  const hidden = useRef({ ms: 0, since: null });
  const turnKey = game?.status === "player_turn" ? `${game.id}:${game.fen}` : null;

  useEffect(() => {
    if (!turnKey) return;
    turnStart.current = performance.now();
    hidden.current = { ms: 0, since: document.hidden ? performance.now() : null };
  }, [turnKey]);

  useEffect(() => {
    function onVisibility() {
      const h = hidden.current;
      if (document.hidden) h.since = performance.now();
      else if (h.since != null) {
        h.ms += performance.now() - h.since;
        h.since = null;
      }
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  function thinkMs() {
    if (turnStart.current == null) return null;
    const now = performance.now();
    const h = hidden.current;
    const hiddenNow = h.since != null ? now - h.since : 0;
    return Math.max(0, Math.round(now - turnStart.current - h.ms - hiddenNow));
  }

  useEffect(() => {
    // React StrictMode runs effects twice in development; only set up once.
    if (started.current) return;
    started.current = true;
    api
      .models()
      .then((m) => {
        setModels(m);
        const saved = remembered(MODEL_KEY);
        setModel(m.models.some((x) => x.id === saved) ? saved : m.default);
      })
      .catch((e) => setError(e.message));

    const savedGame = remembered(GAME_KEY);
    const resume = savedGame ? api.getGame(savedGame).catch(() => null) : Promise.resolve(null);
    // A game started automatically on page load is always casual: rated games are a choice.
    // Only resume a game in a state this version understands: games left waiting on the
    // old mid-game coach question are set aside.
    // A finished game reopens on its review.
    const resumable = (g) =>
      g && ["player_turn", "warned", "finished"].includes(g.status);
    resume.then((g) => (resumable(g) ? g : api.newGame("white", false)))
      .then((g) => {
        setGame(g);
        remember(GAME_KEY, String(g.id));
      })
      .catch((e) => setError(e.message));
  }, []);

  // Load the review when a game finishes; drop it when a new game starts.
  useEffect(() => {
    if (!finishedId) return;
    let live = true;
    api
      .review(finishedId)
      .then((r) => live && setReview(r))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [finishedId]);

  async function runReview(kind, fn) {
    setReviewBusy(kind);
    setError(null);
    try {
      setReview(await fn());
    } catch (e) {
      setError(e.message);
    } finally {
      setReviewBusy(null);
    }
  }

  function onSummary() {
    runReview("summary", () => api.reviewSummary(finishedId, model));
  }

  function focusMoment(item, line, arrow) {
    setFocus({
      gameId: finishedId,
      id: item.move_id,
      label: `Move ${item.move_number} · ${item.san}`,
      fenBefore: item.fen_before,
      line,
      arrow,
    });
    setFrame(0);
  }

  async function run(kind, fn) {
    setBusy(kind);
    setError(null);
    try {
      const g = await fn();
      setGame(g);
    } catch (e) {
      setError(e.message);
      // Resync with the server so the board never shows a move the server rejected.
      if (game) setGame(await api.getGame(game.id).catch(() => game));
    } finally {
      setBusy(null);
    }
  }

  function onMove(uci) {
    const ms = thinkMs();
    // Show the player's move immediately; the server's response then replaces this state.
    const local = new Chess(game.fen);
    local.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    setGame({ ...game, fen: local.fen(), last_move: { uci, by: "player" } });
    run("bot", () => api.move(game.id, uci, ms));
  }

  function newGame(color) {
    run("bot", async () => {
      const g = await api.newGame(color, rated);
      remember(GAME_KEY, String(g.id));
      return g;
    });
  }

  function chooseRated(value) {
    setRated(value);
    remember(RATED_KEY, String(value));
  }

  function chooseModel(id) {
    setModel(id);
    remember(MODEL_KEY, id);
  }

  const interactive = game?.status === "player_turn" && !busy;
  // A focused mistake follows its card: answering or skipping reveals the line and arrow.
  const card = review?.mistakes.find((c) => c.move_id === focus?.id);
  const frames =
    finishedId && focus
      ? framesFor(focus.fenBefore, card ? card.their_line_uci : focus.line)
      : null;
  const at = frames ? Math.min(frame, frames.length - 1) : 0;
  const shown = frames
    ? { ...frames[at], arrow: at === 0 ? (card ? card.best_uci : focus.arrow) : null }
    : null;
  const spend = game?.spend ?? models?.spend;

  return (
    <div className="flex h-full flex-col">

      {error && (
        <div className="bg-bad/20 px-5 py-2 text-sm text-bad" role="alert">
          {error}
        </div>
      )}
      {models && models.models.length === 0 && (
        <div className="bg-warn/20 px-5 py-2 text-sm text-warn">
          No coach models available. Check the API keys in .env and restart. Details:{" "}
          {Object.entries(models.unavailable).map(([k, v]) => `${k}: ${v}`).join("; ")}
        </div>
      )}

      <main className="flex flex-1 flex-col gap-5 overflow-hidden p-5 lg:flex-row">
        <div className="flex flex-1 flex-col items-center justify-center gap-3">
          {game ? (
            <div className="relative flex w-full justify-center">
            <Board
              key={game.id}
              fen={shown ? shown.fen : game.fen}
              orientation={game.player_color}
              interactive={interactive}
              lastMove={shown ? shown.lastMove : game.last_move?.uci}
              onMove={onMove}
              arrow={shown?.arrow}
            />
            </div>
          ) : (
            <div className="text-ink-dim">Setting up the board…</div>
          )}
          {shown && (
            <div className="flex items-center gap-3 text-sm">
              <button
                type="button"
                aria-label="Previous position"
                onClick={() => setFrame(Math.max(0, at - 1))}
                disabled={at === 0}
                className="rounded-md bg-panel-2 px-3 py-1 disabled:opacity-40"
              >
                ◀
              </button>
              <span className="tabular-nums text-ink-dim">
                {focus.label} · {at === 0 ? "before the move" : `move ${at} of ${frames.length - 1}`}
              </span>
              <button
                type="button"
                aria-label="Next position"
                onClick={() => setFrame(Math.min(frames.length - 1, at + 1))}
                disabled={at >= frames.length - 1}
                className="rounded-md bg-panel-2 px-3 py-1 disabled:opacity-40"
              >
                ▶
              </button>
              <button
                type="button"
                onClick={() => setFocus(null)}
                className="text-xs text-ink-dim hover:text-ink"
              >
                final position
              </button>
            </div>
          )}
        </div>
        <aside className="flex min-h-0 w-full flex-col gap-3 lg:w-[400px]">
          <div className="min-h-0 flex-1">
            {finishedId ? (
              <ReviewPanel
                game={game}
                review={review}
                focusId={focus?.id}
                onFocus={focusMoment}
                busy={reviewBusy}
                onAnswer={(moveId, text) =>
                  runReview(moveId, () => api.reviewAnswer(finishedId, moveId, text, model))
                }
                onSkip={(moveId) => runReview(moveId, () => api.reviewSkip(finishedId, moveId))}
                onReveal={(moveId) =>
                  runReview(`reveal-${moveId}`, () =>
                    api.reviewReveal(finishedId, moveId, model),
                  )
                }
                onSummary={onSummary}
              />
            ) : (
              <CoachPanel
                game={game}
                busy={busy}
                onAnswerWarning={(takeBack) =>
                  run(takeBack ? null : "bot", () => api.answerWarning(game.id, takeBack))
                }
              />
            )}
          </div>
          <Controls
            models={models?.models}
            model={model}
            onModel={chooseModel}
            spend={spend}
            onNewGame={newGame}
            onResign={() => run(null, () => api.resign(game.id))}
            canResign={game && game.status !== "finished"}
            rating={game?.player_rating ?? models?.player_rating}
            rated={rated}
            onRated={chooseRated}
            game={game}
          />
        </aside>
      </main>
    </div>
  );
}
