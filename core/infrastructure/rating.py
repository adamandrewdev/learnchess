"""Player rating vs the bot (PLAN D26). Plain Elo, measured on Maia's scale.

- Only rated games count (user's choice: a Rated switch per game, so quick test games don't).
- K is larger while provisional, so the first games find your level fast, then settles.
- Take-backs reduce how much a *gain* counts (user's choice: coached wins count for less).
  Losses count in full: take-backs didn't save that game, so the coach didn't flatter it.
- The next rated game's bot is set to your current rating: expected score ~50%.
"""

from __future__ import annotations

from dataclasses import dataclass

START_RATING = 400  # user's chess.com rating at the start (4 Nov 2026)
PROVISIONAL_GAMES = 10
K_PROVISIONAL = 48
K_ESTABLISHED = 24
BOT_MIN, BOT_MAX = 100, 2500  # Maia-3 accepts 0-5000; keep to the range it was trained on


@dataclass(frozen=True)
class RatingChange:
    before: int
    after: int
    expected: float  # expected score vs this bot, 0..1
    score: float  # 1 win, 0.5 draw, 0 loss
    k: int
    takebacks: int
    weight: float  # applied to gains only

    @property
    def delta(self) -> int:
        return self.after - self.before


def expected_score(player: float, bot: float) -> float:
    return 1 / (1 + 10 ** ((bot - player) / 400))


def takeback_weight(takebacks: int) -> float:
    """1 take-back -> 67%, 2 -> 50%, 4 -> 33%: still worth winning, never worth farming."""
    return 1 / (1 + 0.5 * takebacks)


def update(
    rating: int, bot_elo: int, score: float, rated_games_so_far: int, takebacks: int
) -> RatingChange:
    k = K_PROVISIONAL if rated_games_so_far < PROVISIONAL_GAMES else K_ESTABLISHED
    exp = expected_score(rating, bot_elo)
    raw = k * (score - exp)
    weight = takeback_weight(takebacks) if raw > 0 else 1.0
    after = round(rating + raw * weight)
    return RatingChange(rating, after, exp, score, k, takebacks, weight)


def bot_elo_for(rating: float) -> int:
    return max(BOT_MIN, min(BOT_MAX, round(rating)))
