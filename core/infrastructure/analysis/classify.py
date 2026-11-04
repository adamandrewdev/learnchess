"""Move classification by win-probability loss (PLAN D6).

Thresholds are on the [0, 1] expected-score scale and are tunable settings.
"""

from __future__ import annotations

from enum import StrEnum


class Quality(StrEnum):
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"


THRESHOLDS = {Quality.BLUNDER: 0.15, Quality.MISTAKE: 0.10, Quality.INACCURACY: 0.05}


def classify(win_prob_before: float, win_prob_after: float) -> tuple[Quality, float]:
    """Both probabilities are for the player who moved. Returns (quality, loss)."""
    loss = max(0.0, win_prob_before - win_prob_after)
    for quality, threshold in THRESHOLDS.items():
        if loss >= threshold:
            return quality, loss
    return Quality.GOOD, loss
