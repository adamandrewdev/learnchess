// Player-facing wording for game results.

export function endHeadline(game) {
  const how = (game.end_reason ?? "").replaceAll("_", " ");
  if (game.end_reason === "resignation") return "You resigned.";
  if (game.outcome_for_player === "win") return `${cap(how)}. You won!`;
  if (game.outcome_for_player === "loss") return `${cap(how)}. You lost.`;
  return `Draw by ${how}.`;
}

function cap(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
