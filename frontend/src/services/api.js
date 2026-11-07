// Thin wrapper over the FastAPI routes in backend/routes.py.

async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `${method} ${path} failed (${res.status})`);
  }
  return data;
}

export const api = {
  models: () => request("GET", "/models"),
  newGame: (color, rated) => request("POST", "/games", { color, rated }),
  getGame: (id) => request("GET", `/games/${id}`),
  // thinkMs: time spent on this move, measured in the browser (PLAN D30).
  move: (id, uci, thinkMs) => request("POST", `/games/${id}/moves`, { uci, think_ms: thinkMs }),
  answerWarning: (id, takeBack) =>
    request("POST", `/games/${id}/warning`, { take_back: takeBack }),
  resign: (id) => request("POST", `/games/${id}/resign`),
  // End-of-game review (PLAN D28).
  review: (id) => request("GET", `/games/${id}/review`),
  reviewAnswer: (id, moveId, text, model) =>
    request("POST", `/games/${id}/review/answer`, { move_id: moveId, text, model }),
  reviewSkip: (id, moveId) => request("POST", `/games/${id}/review/skip`, { move_id: moveId }),
  reviewReveal: (id, moveId, model) =>
    request("POST", `/games/${id}/review/reveal`, { move_id: moveId, model }),
  reviewSummary: (id, model) => request("POST", `/games/${id}/review/summary`, { model }),
};
