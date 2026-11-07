import { endHeadline } from "../services/gameText.js";
import MoveList from "./MoveList.jsx";

// Quiet play (PLAN D27): the coach says nothing during the game except a one-line warning
// when a move drops material or allows mate. The "why?" questions move to the end-of-game
// review (D28).

const PRIMARY = "rounded-md bg-warn px-3 py-1.5 text-sm font-semibold text-felt";
const SECONDARY = "rounded-md bg-panel-2 px-3 py-1.5 text-sm font-semibold hover:bg-line";

function Thinking({ label }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-dim" role="status">
      <span className="inline-flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent"
            style={{ animationDelay: `${i * 120}ms` }}
          />
        ))}
      </span>
      {label}
    </div>
  );
}

export default function CoachPanel({ game, busy, onAnswerWarning }) {
  const status = game?.status;
  return (
    <section className="flex h-full min-h-0 flex-col gap-3 rounded-lg bg-panel p-4">
      <MoveList moves={game?.moves ?? []} />

      <div className="min-h-0 flex-1" />

      {status === "warned" && !busy && (
        <div className="rounded-lg border border-warn/60 bg-warn/10 p-3" role="alert">
          <p className="text-sm font-semibold text-warn">{game.warning}</p>
          <div className="mt-2 flex gap-2">
            <button onClick={() => onAnswerWarning(true)} className={`flex-1 ${PRIMARY}`}>
              Take back
            </button>
            <button onClick={() => onAnswerWarning(false)} className={`flex-1 ${SECONDARY}`}>
              Keep my move
            </button>
          </div>
          {game.rated && (
            <p className="mt-2 text-[11px] text-ink-dim">
              Rated game: take-backs reduce what a win is worth.
            </p>
          )}
        </div>
      )}

      {busy === "bot" && <Thinking label="Opponent is thinking…" />}
      {status === "player_turn" && !busy && (
        <p className="text-center text-xs text-ink-dim">
          Your move. I'll only speak up if a move loses material or allows checkmate.
        </p>
      )}
      {status === "finished" && <p className="text-center text-sm">{endHeadline(game)}</p>}
    </section>
  );
}
