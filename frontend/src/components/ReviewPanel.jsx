import { useEffect, useRef, useState } from "react";
import { endHeadline } from "../services/gameText.js";

// End-of-game review (PLAN D28): what went well, the costliest moves (asked "why?" about those
// only), and thinking patterns against your usual. Picking a moment shows it on the board.

const QUICK_REPLIES = [
  "I was attacking something",
  "I was defending something",
  "Getting a piece out",
  "I didn't see what they were threatening",
  "It just looked like a good move",
  "No idea, honestly",
];

const QUALITY_STYLE = { mistake: "text-warn", blunder: "text-bad" };
const QUIET =
  "rounded-md px-2 py-1.5 text-xs text-ink-dim ring-1 ring-line hover:text-ink hover:ring-ink-dim";
const PRIMARY = "rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-felt disabled:opacity-40";

function Section({ title, children }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-dim">{title}</h3>
      {children}
    </section>
  );
}

function Pending({ label }) {
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

function MomentButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg px-3 py-2 text-left text-sm ring-1 ${
        active ? "bg-panel-2 ring-accent" : "ring-line hover:ring-ink-dim"
      }`}
    >
      {children}
    </button>
  );
}

function MistakeCard({ card, active, onFocus, busy, onAnswer, onSkip, onReveal }) {
  const [text, setText] = useState("");
  const open = !card.reply && !card.skipped;
  function send(reason) {
    if (!reason.trim()) return;
    onAnswer(card.move_id, reason.trim());
    setText("");
  }
  return (
    <div className={`space-y-2 rounded-lg p-3 ring-1 ${active ? "ring-accent" : "ring-line"}`}>
      <button type="button" onClick={onFocus} className="w-full text-left text-sm">
        <span className="text-ink-dim">Move {card.move_number} · </span>
        <span className="font-semibold">{card.san}</span>
        <span className={`ml-2 text-xs uppercase ${QUALITY_STYLE[card.quality]}`}>
          {card.quality}
        </span>
        {card.caught_by_warning && (
          <span className="ml-2 text-xs text-ink-dim">· caught by the warning, taken back</span>
        )}
        {card.played_anyway && (
          <span className="ml-2 text-xs text-ink-dim">· played anyway after a warning</span>
        )}
      </button>
      <p className="text-sm">{card.question}</p>

      {open && busy !== card.move_id && (
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
            <input
              aria-label={`Why you played ${card.san}`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="min-w-0 flex-1 rounded-md bg-felt px-3 py-1.5 text-sm outline-none ring-1 ring-line focus:ring-accent"
              placeholder="Or in your own words…"
            />
            <button type="submit" disabled={!text.trim()} className={PRIMARY}>
              Send
            </button>
          </form>
          <button type="button" onClick={() => onSkip(card.move_id)} className={QUIET}>
            Skip this one
          </button>
        </div>
      )}
      {busy === card.move_id && <Pending label="Coach is thinking…" />}

      {card.player_reason && (
        <div className="ml-4 rounded-lg bg-panel-2 px-3 py-2 text-sm">{card.player_reason}</div>
      )}
      {card.reply && <p className="text-sm leading-relaxed">{card.reply}</p>}
      {card.skipped && <p className="text-xs text-ink-dim">Skipped.</p>}

      {!open && (
        <div className="space-y-1 text-sm">
          {card.their_line_san.length > 0 && (
            <p>
              <span className="text-ink-dim">Their best reply: </span>
              {card.their_line_san.join(" ")}
              <button type="button" onClick={onFocus} className="ml-2 text-xs text-accent">
                step through
              </button>
            </p>
          )}
          {card.best_move_san && (
            <p>
              <span className="text-ink-dim">Better was </span>
              <span className="font-semibold text-accent">{card.best_move_san}</span>
            </p>
          )}
          {card.reveal_reply ? (
            <p className="rounded-lg border border-accent/50 bg-accent/10 px-3 py-2 leading-relaxed">
              {card.reveal_reply}
            </p>
          ) : (
            card.best_move_san &&
            busy !== `reveal-${card.move_id}` && (
              <button type="button" onClick={() => onReveal(card.move_id)} className={QUIET}>
                Why is {card.best_move_san} better?
              </button>
            )
          )}
          {busy === `reveal-${card.move_id}` && <Pending label="Coach is thinking…" />}
        </div>
      )}
    </div>
  );
}

function pct(c) {
  return c.opportunities ? Math.round((100 * c.hits) / c.opportunities) : null;
}

function PatternRow({ p }) {
  const now = pct(p.this_game);
  const usual = p.usual.opportunities >= 5 ? pct(p.usual) : null;
  if (now === null) return null;
  const misses = p.this_game.opportunities - p.this_game.hits;
  const tone = usual === null ? "" : now >= usual ? "text-good" : "text-bad";
  return (
    <li className="flex items-baseline justify-between gap-3 text-sm">
      <span>
        {p.strength}
        {misses > 0 && (
          <span className="ml-1 text-xs text-bad">
            · {p.weakness.toLowerCase()} ×{misses}
          </span>
        )}
      </span>
      <span className="shrink-0 tabular-nums">
        <span className={tone}>
          {p.this_game.hits}/{p.this_game.opportunities}
        </span>
        {usual !== null && <span className="text-xs text-ink-dim"> · usually {usual}%</span>}
      </span>
    </li>
  );
}

function Caught({ w }) {
  const caught = w.this_game.taken_back;
  if (!caught && w.usual_taken_back_per_game === null) return null;
  return (
    <p className="text-sm">
      {caught ? (
        <>
          The warning caught{" "}
          <span className="font-semibold text-warn">
            {caught} blunder{caught === 1 ? "" : "s"}
          </span>{" "}
          you were about to make.
        </>
      ) : (
        "The warning didn't need to step in."
      )}
      {w.usual_taken_back_per_game !== null && (
        <span className="text-xs text-ink-dim">
          {" "}
          · usually {w.usual_taken_back_per_game} per game
        </span>
      )}
    </p>
  );
}

function Timing({ t }) {
  const fmt = (x) => (x === null ? "–" : `${x}s`);
  const now = t.this_game;
  if (now.ok_moves === null && now.bad_moves === null) return null;
  return (
    <p className="text-sm">
      <span className="text-ink-dim">Thinking time (median): </span>
      good moves {fmt(now.ok_moves)}, mistakes {fmt(now.bad_moves)}
      {(t.usual.ok_moves !== null || t.usual.bad_moves !== null) && (
        <span className="text-xs text-ink-dim">
          {" "}
          · usually {fmt(t.usual.ok_moves)} / {fmt(t.usual.bad_moves)}
        </span>
      )}
    </p>
  );
}

export default function ReviewPanel({
  game,
  review,
  focusId,
  onFocus,
  busy,
  onAnswer,
  onSkip,
  onReveal,
  onSummary,
}) {
  const asked = useRef(false);
  const n = review?.numbers;
  const allDone = review?.mistakes.every((c) => c.reply || c.skipped);

  // Write the summary once every question is answered or skipped (it can use the answers).
  useEffect(() => {
    if (review && allDone && !review.summary && !asked.current) {
      asked.current = true;
      onSummary();
    }
  }, [review, allDone, onSummary]);

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg bg-panel">
      <header className="border-b border-line px-4 py-3">
        <div className="font-semibold">{endHeadline(game)}</div>
        <div className="text-xs text-ink-dim">
          Game review
          {game.rating_change &&
            ` · rating ${game.rating_change.after} (${game.rating_change.delta >= 0 ? "+" : ""}${game.rating_change.delta})`}
          {review?.excluded && " · not counted in your profile"}
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-4">
        {!review && <Pending label="Putting your review together…" />}

        {review && (
          <>
            <Section title="What went well">
              {review.highlights.length === 0 && (
                <p className="text-sm text-ink-dim">Nothing stood out this game.</p>
              )}
              {review.highlights.map((h) => (
                <MomentButton
                  key={h.move_id}
                  active={focusId === h.move_id}
                  onClick={() => onFocus(h, h.line_uci, null)}
                >
                  <span className="text-ink-dim">Move {h.move_number} · </span>
                  <span className="font-semibold text-good">{h.san}</span>
                  <div>{h.text}</div>
                </MomentButton>
              ))}
            </Section>

            <Section title="Your costliest moves">
              <Caught w={n.warnings} />
              {review.mistakes.length === 0 && (
                <p className="text-sm text-ink-dim">No mistakes or blunders. Nice.</p>
              )}
              {review.mistakes.map((c) => (
                <MistakeCard
                  key={c.move_id}
                  card={c}
                  active={focusId === c.move_id}
                  onFocus={() => onFocus(c, c.their_line_uci, c.best_uci)}
                  busy={busy}
                  onAnswer={onAnswer}
                  onSkip={onSkip}
                  onReveal={onReveal}
                />
              ))}
            </Section>

            <Section title="Your patterns">
              {n.history_games < 3 && (
                <p className="text-xs text-ink-dim">
                  Based on {n.history_games} earlier game{n.history_games === 1 ? "" : "s"}; this
                  gets clearer as you play.
                </p>
              )}
              <ul className="space-y-1.5">
                {n.patterns.map((p) => (
                  <PatternRow key={p.key} p={p} />
                ))}
              </ul>
              <Timing t={n.think_seconds} />

              {review.summary ? (
                <div className="space-y-2 rounded-lg bg-panel-2 p-3 text-sm leading-relaxed">
                  <p>{review.summary.went_well}</p>
                  <p>{review.summary.patterns}</p>
                  <p>
                    <span className="font-semibold text-good">Keep doing: </span>
                    {review.summary.keep_doing}
                  </p>
                  <p>
                    <span className="font-semibold text-warn">Work on: </span>
                    {review.summary.work_on}
                  </p>
                </div>
              ) : busy === "summary" ? (
                <Pending label="Writing your summary…" />
              ) : (
                <button type="button" onClick={onSummary} className={QUIET}>
                  {allDone ? "Write my summary" : "Skip the questions and write my summary"}
                </button>
              )}
            </Section>
          </>
        )}
      </div>
    </section>
  );
}
