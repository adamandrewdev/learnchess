import { useEffect, useRef, useState } from "react";
import { Chess } from "chess.js";
import { api } from "./services/api.js";
import Board from "./components/Board.jsx";
import CoachPanel from "./components/CoachPanel.jsx";
import { endHeadline } from "./services/gameText.js";
import Controls from "./components/Controls.jsx";

const MODEL_KEY = "learnchess.model";
const GAME_KEY = "learnchess.gameId";
const RATED_KEY = "learnchess.rated";

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
  const [busy, setBusy] = useState(null); // null | "bot" | "coach"
  const [error, setError] = useState(null);
  const [rated, setRated] = useState(() => remembered(RATED_KEY) === "true");
  const started = useRef(false);

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
    resume.then((g) => (g && g.status !== "finished" ? g : api.newGame("white", false)))
      .then((g) => {
        setGame(g);
        remember(GAME_KEY, String(g.id));
      })
      .catch((e) => setError(e.message));
  }, []);

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
    // Show the player's move immediately; the server's response then replaces this state.
    const local = new Chess(game.fen);
    local.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    setGame({ ...game, fen: local.fen(), last_move: { uci, by: "player" } });
    run("bot", () => api.move(game.id, uci));
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
  // After "show me" + take-back, the board is back on the position the best move belongs to.
  const lastEx = game?.coach_log?.at(-1);
  // Only while the board is still on that exact position: gone as soon as anyone moves.
  const arrow =
    game?.status === "player_turn" && lastEx?.best_move_uci && lastEx.fen_before === game.fen
      ? lastEx.best_move_uci
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
              fen={game.fen}
              orientation={game.player_color}
              interactive={interactive}
              lastMove={game.last_move?.uci}
              onMove={onMove}
              arrow={arrow}
            />
            {game.status === "finished" && (
              <div className="absolute inset-0 z-50 flex items-center justify-center">
                <div className="rounded-xl bg-felt/95 px-8 py-6 text-center shadow-2xl ring-1 ring-line">
                  <div className="text-2xl font-bold">{endHeadline(game)}</div>
                  {game.rating_change && (
                    <div className="mt-2 text-lg tabular-nums">
                      Rating {game.rating_change.before} → {game.rating_change.after}{" "}
                      <span
                        className={
                          game.rating_change.delta >= 0 ? "text-good" : "text-bad"
                        }
                      >
                        ({game.rating_change.delta >= 0 ? "+" : ""}
                        {game.rating_change.delta})
                      </span>
                      {game.rating_change.takebacks > 0 && game.rating_change.weight < 1 && (
                        <div className="text-xs text-ink-dim">
                          {game.rating_change.takebacks} take-back
                          {game.rating_change.takebacks === 1 ? "" : "s"}: win counted at{" "}
                          {Math.round(game.rating_change.weight * 100)}%
                        </div>
                      )}
                    </div>
                  )}
                  {!game.rated && (
                    <div className="mt-2 text-xs text-ink-dim">Casual game: rating unchanged</div>
                  )}
                  <div className="mt-1 text-sm text-ink-dim">
                    {Math.ceil(game.moves.length / 2)} moves · {game.coach_log.length} coach{" "}
                    {game.coach_log.length === 1 ? "conversation" : "conversations"}
                  </div>
                  <div className="mt-5 flex gap-3">
                    <button
                      onClick={() => newGame("white")}
                      className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-felt"
                    >
                      New game as white
                    </button>
                    <button
                      onClick={() => newGame("black")}
                      className="rounded-md bg-panel-2 px-4 py-2 text-sm font-semibold"
                    >
                      New game as black
                    </button>
                  </div>
                </div>
              </div>
            )}
            </div>
          ) : (
            <div className="text-ink-dim">Setting up the board…</div>
          )}
        </div>
        <aside className="flex min-h-0 w-full flex-col gap-3 lg:w-[400px]">
          <div className="min-h-0 flex-1">
            <CoachPanel
              game={game}
              busy={busy}
              onReason={(text) => run("coach", () => api.reason(game.id, text, model))}
              onContinue={(retry, force = false) =>
                run(retry ? null : "bot", () => api.continueGame(game.id, retry, force))
              }
              onReveal={() => run("coach", () => api.reveal(game.id, model))}
            />
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
