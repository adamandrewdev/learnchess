import { useEffect, useState } from "react";
import { api } from "../services/api.js";

// Playstyle profile (PLAN D31). Patterns first, rating last and small: the point is how you
// play, not the number. Every figure comes from the backend's counts; nothing here is LLM text.

const PCT = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);

function Card({ title, note, children }) {
  return (
    <section className="space-y-3 rounded-lg bg-panel p-4">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-dim">{title}</h2>
        {note && <p className="mt-1 text-xs text-ink-dim">{note}</p>}
      </div>
      {children}
    </section>
  );
}

function Bar({ value, tone = "bg-accent" }) {
  return (
    <div className="h-1.5 w-full rounded-full bg-felt">
      <div
        className={`h-1.5 rounded-full ${tone}`}
        style={{ width: `${Math.round((value ?? 0) * 100)}%` }}
      />
    </div>
  );
}

function Trend({ value }) {
  if (value == null) return <span className="text-xs text-ink-dim">no trend yet</span>;
  const pts = Math.round(value * 100);
  if (pts === 0) return <span className="text-xs text-ink-dim">steady</span>;
  return (
    <span className={`text-xs tabular-nums ${pts > 0 ? "text-accent" : "text-warn"}`}>
      {pts > 0 ? "▲" : "▼"} {Math.abs(pts)} pts
    </span>
  );
}

function Headline({ profile }) {
  const byKey = Object.fromEntries(profile.patterns.map((p) => [p.key, p]));
  const s = byKey[profile.headline.strength];
  const w = byKey[profile.headline.weakness];
  if (!s && !w) return null;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {s && (
        <div className="rounded-lg bg-panel p-4 ring-1 ring-accent/40">
          <div className="text-xs uppercase tracking-wide text-accent">Your strongest habit</div>
          <div className="mt-1 text-lg font-semibold">{s.strength}</div>
          <div className="text-sm text-ink-dim">
            {s.recent.hits} of {s.recent.opportunities} chances ({PCT(s.recent.rate)}) over your
            last {profile.window} games
          </div>
        </div>
      )}
      {w && (
        <div className="rounded-lg bg-panel p-4 ring-1 ring-warn/40">
          <div className="text-xs uppercase tracking-wide text-warn">Most room to grow</div>
          <div className="mt-1 text-lg font-semibold">{w.weakness}</div>
          <div className="text-sm text-ink-dim">
            {w.recent.opportunities - w.recent.hits} of {w.recent.opportunities} chances over your
            last {profile.window} games
          </div>
        </div>
      )}
    </div>
  );
}

function Patterns({ profile }) {
  const rows = [...profile.patterns].sort(
    (a, b) => (b.recent.rate ?? -1) - (a.recent.rate ?? -1),
  );
  return (
    <Card
      title={`Patterns · last ${profile.window} games`}
      note={`How often you got it right when the chance came up. Trend compares with the ${profile.window} games before.`}
    >
      <ul className="space-y-3">
        {rows.map((p) => {
          const enough = p.recent.opportunities >= profile.min_opportunities;
          const misses = p.recent.opportunities - p.recent.hits;
          return (
            <li key={p.key} className="space-y-1">
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span>{p.strength}</span>
                <span className="shrink-0 tabular-nums text-ink-dim">
                  {enough ? (
                    <>
                      {p.recent.hits}/{p.recent.opportunities} · <Trend value={p.trend} />
                    </>
                  ) : (
                    `not enough yet (${p.recent.opportunities} chances)`
                  )}
                </span>
              </div>
              {enough && <Bar value={p.recent.rate} />}
              {enough && misses > 0 && (
                <div className="text-xs text-ink-dim">
                  {p.weakness}: {misses}×
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

const SPLIT_LABELS = {
  phase: { title: "By phase", order: ["opening", "middlegame", "endgame"] },
  color: { title: "By colour", order: ["white", "black"] },
  eval_state: { title: "By position", order: ["ahead", "level", "behind"] },
};
const NAMES = {
  opening: "Opening",
  middlegame: "Middlegame",
  endgame: "Endgame",
  white: "As white",
  black: "As black",
  ahead: "When ahead",
  level: "When level",
  behind: "When behind",
};

function FallApart({ breakdowns }) {
  return (
    <Card
      title="Where games fall apart"
      note="Share of your moves the engine calls a mistake or blunder. Opening moves are graded strictly, so that number runs high."
    >
      <div className="grid gap-4 sm:grid-cols-3">
        {Object.entries(SPLIT_LABELS).map(([key, { title, order }]) => {
          const split = breakdowns[key] ?? {};
          const worst = Math.max(...order.map((k) => split[k]?.bad_rate ?? 0));
          return (
            <div key={key} className="space-y-2">
              <div className="text-xs text-ink-dim">{title}</div>
              {order.map((k) => {
                const s = split[k];
                if (!s) return null;
                return (
                  <div key={k} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span>{NAMES[k] ?? k}</span>
                      <span className="tabular-nums text-ink-dim">{PCT(s.bad_rate)}</span>
                    </div>
                    <Bar
                      value={s.bad_rate}
                      tone={s.bad_rate === worst && worst > 0 ? "bg-warn" : "bg-ink-dim"}
                    />
                    <div className="text-xs text-ink-dim">
                      {s.bad_moves} of {s.moves} moves
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function Seconds({ label, value, min }) {
  return (
    <div className="flex items-baseline justify-between text-sm">
      <span>{label}</span>
      {value.median_s != null ? (
        <span className="tabular-nums">{value.median_s} s</span>
      ) : (
        <span className="text-xs text-ink-dim">
          {value.moves} of {min} moves needed
        </span>
      )}
    </div>
  );
}

function Timing({ timing }) {
  const min = timing.min_moves;
  return (
    <Card
      title="How long you think"
      note={`Typical (median) time before a move, from ${timing.timed_moves} timed moves. Time with the tab hidden doesn't count.`}
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <div className="text-xs text-ink-dim">Before…</div>
          <Seconds label="good moves" value={timing.ok_vs_bad.ok} min={min} />
          <Seconds label="mistakes & blunders" value={timing.ok_vs_bad.bad} min={min} />
        </div>
        <div className="space-y-1.5">
          <div className="text-xs text-ink-dim">In the…</div>
          {["opening", "middlegame", "endgame"].map((p) => (
            <Seconds key={p} label={p} value={timing.by_phase[p]} min={min} />
          ))}
        </div>
        <div className="space-y-1.5">
          <div className="text-xs text-ink-dim">When their last move…</div>
          <Seconds label="threatened something" value={timing.after_threat.threat} min={min} />
          <Seconds label="didn't" value={timing.after_threat.no_threat} min={min} />
        </div>
      </div>
    </Card>
  );
}

function Traps({ traps }) {
  const top = traps[0]?.count ?? 1;
  return (
    <Card
      title="Thinking traps, from your answers"
      note="When you said why you played a mistake, the coach labelled the thinking behind it."
    >
      {traps.length === 0 ? (
        <p className="text-sm text-ink-dim">No answers yet.</p>
      ) : (
        <ul className="space-y-2">
          {traps.map((t) => (
            <li key={t.trap} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span>{t.label}</span>
                <span className="tabular-nums text-ink-dim">{t.count}×</span>
              </div>
              <Bar value={t.count / top} tone="bg-ink-dim" />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function RatingLine({ points }) {
  if (points.length < 2) return null;
  const w = 320;
  const h = 64;
  const ys = points.map((p) => p.rating);
  const lo = Math.min(...ys) - 10;
  const hi = Math.max(...ys) + 10;
  const x = (i) => (i / (points.length - 1)) * w;
  const y = (r) => h - ((r - lo) / (hi - lo)) * h;
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.rating).toFixed(1)}`);
  const last = points[points.length - 1];
  return (
    <div className="space-y-1">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="h-16 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Rating over ${points.length} rated games, now ${last.rating}`}
      >
        <path
          d={d.join(" ")}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="flex justify-between text-xs text-ink-dim tabular-nums">
        <span>{points[0].rating}</span>
        <span>
          now {last.rating} · {points.length} rated games
        </span>
      </div>
    </div>
  );
}

const OUTCOME = { win: "Won", loss: "Lost", draw: "Draw" };

function Games({ games, onOpenGame }) {
  return (
    <Card title="Games" note="Open one to see its review.">
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-sm">
          <tbody>
            {games.map((g) => (
              <tr
                key={g.id}
                onClick={() => onOpenGame(g.id)}
                className="cursor-pointer border-t border-line hover:bg-panel-2"
              >
                <td className="py-1.5 pr-2 tabular-nums text-ink-dim">#{g.id}</td>
                <td className="pr-2 tabular-nums text-ink-dim">{g.date.slice(5)}</td>
                <td className="pr-2">
                  {OUTCOME[g.outcome] ?? "–"}
                  <span className="text-ink-dim"> as {g.color}</span>
                </td>
                <td className="pr-2 tabular-nums text-ink-dim">{g.moves} moves</td>
                <td className="pr-2 tabular-nums text-ink-dim">
                  {g.mistakes} mistake{g.mistakes === 1 ? "" : "s"}
                  {g.caught > 0 && ` · ${g.caught} caught`}
                </td>
                <td className="text-right text-xs text-ink-dim">
                  {g.excluded
                    ? "not counted"
                    : g.rated
                      ? `rated ${g.rating_delta > 0 ? "+" : ""}${g.rating_delta ?? ""}`
                      : "casual"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function ProfilePage({ onBack, onOpenGame }) {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    api
      .profile()
      .then((p) => live && setProfile(p))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-4 p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Your playstyle</h1>
            {profile && (
              <p className="text-sm text-ink-dim">
                From {profile.games_counted} finished games
                {profile.games_excluded > 0 && ` (${profile.games_excluded} not counted)`}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onBack}
            className="rounded-md bg-panel-2 px-3 py-1.5 text-sm hover:bg-line"
          >
            Back to the board
          </button>
        </div>

        {error && (
          <div className="rounded-md bg-bad/20 px-3 py-2 text-sm text-bad" role="alert">
            {error}
          </div>
        )}
        {!profile && !error && <p className="text-sm text-ink-dim">Counting your games…</p>}

        {profile && (
          <>
            <Headline profile={profile} />
            <div className="grid gap-4 lg:grid-cols-2">
              <Patterns profile={profile} />
              <div className="space-y-4">
                <Traps traps={profile.traps} />
                <Card title="Rating">
                  {profile.rating.length >= 2 ? (
                    <RatingLine points={profile.rating} />
                  ) : (
                    <p className="text-sm text-ink-dim">Play two rated games to see a line.</p>
                  )}
                </Card>
              </div>
            </div>
            <FallApart breakdowns={profile.breakdowns} />
            <Timing timing={profile.timing} />
            <Games games={profile.games} onOpenGame={onOpenGame} />
          </>
        )}
      </div>
    </div>
  );
}
