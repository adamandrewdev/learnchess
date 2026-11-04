// Bottom-right panel: new game, resign, coach model (PLAN D10) and spend vs cap (D11).
// Replaces the old top bar (user feedback: free the space, put the options here).

export default function Controls({
  models,
  model,
  onModel,
  spend,
  onNewGame,
  onResign,
  canResign,
  rating,
  rated,
  onRated,
  game,
}) {
  const pct = spend ? Math.min(100, (100 * spend.month_usd) / (spend.cap_usd || 1)) : 0;
  return (
    <section className="space-y-3 rounded-lg bg-panel p-4">
      <div className="flex items-center justify-between">
        <span className="font-bold tracking-tight">
          learn<span className="text-accent">chess</span>
        </span>
        {canResign && (
          <button onClick={onResign} className="text-xs text-bad hover:underline">
            Resign
          </button>
        )}
      </div>

      {rating && (
        <div className="flex items-baseline justify-between">
          <div>
            <span className="text-2xl font-bold tabular-nums">{rating.rating}</span>
            <span className="ml-2 text-xs text-ink-dim">
              your rating
              {rating.provisional && ` · provisional (${rating.rated_games}/10 rated games)`}
            </span>
          </div>
        </div>
      )}
      {game && (
        <div className="text-xs text-ink-dim">
          This game: {game.rated ? "rated" : "casual"} · opponent {game.bot_elo}
        </div>
      )}

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={rated}
          onChange={(e) => onRated(e.target.checked)}
          className="h-4 w-4 accent-[var(--color-accent)]"
        />
        <span>Rated</span>
        <span className="text-xs text-ink-dim">(next game counts towards your rating)</span>
      </label>

      <div className="flex gap-2">
        <button
          onClick={() => onNewGame("white")}
          className="flex-1 rounded-md bg-panel-2 px-3 py-1.5 text-sm hover:bg-line"
        >
          New game (white)
        </button>
        <button
          onClick={() => onNewGame("black")}
          className="flex-1 rounded-md bg-panel-2 px-3 py-1.5 text-sm hover:bg-line"
        >
          New game (black)
        </button>
      </div>

      <label className="flex items-center justify-between gap-2 text-sm">
        <span className="text-ink-dim">Coach model</span>
        <select
          value={model ?? ""}
          onChange={(e) => onModel(e.target.value)}
          className="rounded-md bg-felt px-2 py-1 ring-1 ring-line"
          disabled={!models?.length}
        >
          {!models?.length && <option value="">no models available</option>}
          {models?.map((m) => (
            <option key={m.id} value={m.id} title={m.note}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      {spend && (
        <div className="text-xs" title="LLM spend this calendar month (UTC)">
          <div className="flex justify-between text-ink-dim">
            <span>Spend this month</span>
            <span>
              ${spend.month_usd.toFixed(2)} / ${spend.cap_usd.toFixed(2)}
            </span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-felt">
            <div
              className={`h-1.5 rounded-full ${pct >= 100 ? "bg-bad" : pct > 75 ? "bg-warn" : "bg-accent"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
    </section>
  );
}
