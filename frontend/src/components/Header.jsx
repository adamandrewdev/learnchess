// Coach-model menu (PLAN D10) and the month's spend against the cap (D11).

export default function Header({ models, model, onModel, spend, onNewGame, onResign, canResign }) {
  const pct = spend ? Math.min(100, (100 * spend.month_usd) / (spend.cap_usd || 1)) : 0;
  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-line bg-panel px-5 py-3">
      <h1 className="mr-auto text-lg font-bold tracking-tight">
        learn<span className="text-accent">chess</span>
      </h1>

      <label className="flex items-center gap-2 text-sm">
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
        <div className="w-44 text-xs" title="LLM spend this calendar month (UTC)">
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

      <div className="flex gap-2">
        <button onClick={() => onNewGame("white")} className="rounded-md bg-panel-2 px-3 py-1.5 text-sm">
          New game (white)
        </button>
        <button onClick={() => onNewGame("black")} className="rounded-md bg-panel-2 px-3 py-1.5 text-sm">
          New game (black)
        </button>
        {canResign && (
          <button onClick={onResign} className="rounded-md px-3 py-1.5 text-sm text-bad ring-1 ring-line">
            Resign
          </button>
        )}
      </div>
    </header>
  );
}
