import { useState } from "react";
import { endHeadline } from "../services/gameText.js";

// The coach conversation for this game, plus the controls for whatever the game is waiting
// on (PLAN D3, D4, D23).

const QUALITY_STYLE = {
  good: "text-good",
  inaccuracy: "text-warn",
  mistake: "text-warn",
  blunder: "text-bad",
};

// Quick replies (user feedback: offer choices as well as free text). Worded so none of them
// hints whether the move was good or bad, and so the trap labeller can still tell them apart.
const QUICK_REPLIES = [
  "I was attacking something",
  "I was defending something",
  "Getting a piece out",
  "I didn't see what they were threatening",
  "It just looked like a good move",
  "No idea, honestly",
];

function qualityLabel(q) {
  return q === "good" ? "good move" : q;
}

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

function Exchange({ ex }) {
  return (
    <div className="space-y-2">
      <div className="text-sm">
        <span className="text-ink-dim">Coach · </span>
        {ex.question}
      </div>
      {ex.skipped && (
        <div className="ml-6 text-xs text-ink-dim">
          Skipped
          {ex.quality && (
            <span className={QUALITY_STYLE[ex.quality]}> · {qualityLabel(ex.quality)}</span>
          )}
          {ex.taken_back && " · move taken back"}
        </div>
      )}
      {ex.player_reason && (
        <div className="ml-6 rounded-lg bg-panel-2 px-3 py-2 text-sm">{ex.player_reason}</div>
      )}
      {ex.reply && (
        <div
          className={`rounded-lg border border-line px-3 py-2 text-sm leading-relaxed ${
            ex.taken_back ? "opacity-70" : ""
          }`}
        >
          {ex.quality && (
            <div
              className={`mb-1 text-xs font-semibold uppercase tracking-wide ${QUALITY_STYLE[ex.quality]}`}
            >
              {qualityLabel(ex.quality)}
            </div>
          )}
          {ex.reply}
          <div className="mt-1 text-[11px] text-ink-dim">
            {[ex.reply_model, ex.taken_back && "move taken back"].filter(Boolean).join(" · ")}
          </div>
        </div>
      )}
      {ex.reveal_reply && (
        <div className="rounded-lg border border-accent/60 bg-accent/10 px-3 py-2 text-sm leading-relaxed">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-accent">
            best move
          </div>
          {ex.reveal_reply}
          {!ex.taken_back && (
            <div className="mt-1 text-[11px] text-ink-dim">
              Take your move back to see it drawn on the board.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const PRIMARY =
  "rounded-md bg-accent px-3 py-2 text-sm font-semibold text-felt disabled:opacity-40";
const SECONDARY = "rounded-md bg-panel-2 px-3 py-2 text-sm font-semibold hover:bg-line";
const QUIET =
  "rounded-md px-2 py-1.5 text-xs text-ink-dim ring-1 ring-line hover:text-ink hover:ring-ink-dim";

export default function CoachPanel({ game, busy, onReason, onContinue, onReveal }) {
  const [text, setText] = useState("");
  const log = game?.coach_log ?? [];
  const current = log.at(-1);
  const status = game?.status;

  function send(reason) {
    if (!reason.trim()) return;
    onReason(reason.trim());
    setText("");
  }

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg bg-panel">
      <header className="border-b border-line px-4 py-3 font-semibold">Coach</header>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {log.length === 0 && (
          <p className="text-sm text-ink-dim">
            Play your moves. When something goes wrong (and now and then when it goes right), I'll
            stop you and ask why you played it.
          </p>
        )}
        {log.map((ex, i) => (
          <Exchange key={i} ex={ex} />
        ))}
        {busy === "coach" && <Thinking label="Coach is thinking…" />}
        {busy === "bot" && <Thinking label="Opponent is thinking…" />}
      </div>

      <footer className="border-t border-line p-3">
        {status === "awaiting_reason" && busy !== "coach" && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1.5">
              {QUICK_REPLIES.map((q) => (
                <button key={q} type="button" onClick={() => send(q)} className={QUIET}>
                  {q}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(text);
              }}
              className="flex gap-2"
            >
              <textarea
                aria-label="Your reason, in your own words"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(text);
                  }
                }}
                rows={2}
                autoFocus
                className="flex-1 resize-none rounded-md bg-felt px-3 py-2 text-sm outline-none ring-1 ring-line focus:ring-accent"
                placeholder="Or say it in your own words…"
              />
              <button type="submit" disabled={!text.trim()} className={PRIMARY}>
                Send
              </button>
            </form>
            <div className="flex gap-2">
              <button type="button" onClick={() => onContinue(true)} className={`flex-1 ${QUIET}`}>
                Skip: take it back
              </button>
              <button type="button" onClick={() => onContinue(false)} className={`flex-1 ${QUIET}`}>
                Skip: keep my move
              </button>
            </div>
          </div>
        )}

        {status === "confirm_takeback" && !busy && (
          <div className="space-y-2">
            <p className="text-sm">
              <span className="font-semibold text-good">That was a good move.</span> Keep it?
            </p>
            <div className="flex gap-2">
              <button onClick={() => onContinue(false)} className={`flex-1 ${PRIMARY}`}>
                Keep my move
              </button>
              <button onClick={() => onContinue(true, true)} className={`flex-1 ${SECONDARY}`}>
                Take it back anyway
              </button>
            </div>
          </div>
        )}

        {status === "coach_replied" && !busy && (
          <div className="space-y-2">
            {!current?.revealed && (
              <button onClick={onReveal} className={`w-full ${QUIET}`}>
                Show me the best move
              </button>
            )}
            <div className="flex gap-2">
              <button
                onClick={() => onContinue(true)}
                className={`flex-1 ${current?.offer_retry ? PRIMARY : SECONDARY}`}
              >
                Take it back and retry
              </button>
              <button
                onClick={() => onContinue(false)}
                className={`flex-1 ${current?.offer_retry ? SECONDARY : PRIMARY}`}
              >
                Keep my move
              </button>
            </div>
          </div>
        )}

        {status === "player_turn" && !busy && (
          <p className="text-center text-xs text-ink-dim">Your move.</p>
        )}
        {status === "finished" && <p className="text-center text-sm">{endHeadline(game)}</p>}
      </footer>
    </section>
  );
}
