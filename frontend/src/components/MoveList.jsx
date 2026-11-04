export default function MoveList({ moves }) {
  const rows = [];
  for (let i = 0; i < moves.length; i += 2) {
    rows.push([i / 2 + 1, moves[i], moves[i + 1]]);
  }
  return (
    <div className="max-h-40 overflow-y-auto rounded-lg bg-panel px-3 py-2 font-mono text-sm">
      {rows.length === 0 ? (
        <span className="text-ink-dim">No moves yet.</span>
      ) : (
        <ol className="grid grid-cols-[2.5rem_1fr_1fr] gap-y-0.5">
          {rows.map(([n, w, b]) => (
            <li key={n} className="contents">
              <span className="text-ink-dim">{n}.</span>
              <span>{w}</span>
              <span>{b ?? ""}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
