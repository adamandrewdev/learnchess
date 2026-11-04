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
  move: (id, uci) => request("POST", `/games/${id}/moves`, { uci }),
  reason: (id, text, model) => request("POST", `/games/${id}/reason`, { text, model }),
  reveal: (id, model) => request("POST", `/games/${id}/reveal`, { model }),
  continueGame: (id, retry, force = false) =>
    request("POST", `/games/${id}/continue`, { retry, force }),
  resign: (id) => request("POST", `/games/${id}/resign`),
};
