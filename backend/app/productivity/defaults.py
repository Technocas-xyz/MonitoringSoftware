"""Default productivity categories (spec 26/27).

Three seed categories with indicator weights. The indicator is a weighted ratio, always
surfaced as a "Productivity/Activity Indicator" — never an absolute performance score.
Weights are configurable per org after seeding.
"""
from __future__ import annotations

# key -> (label, weight). Weight feeds the indicator formula.
DEFAULT_CATEGORIES: dict[str, tuple[str, float]] = {
    "productive": ("Productive", 1.0),
    "neutral": ("Neutral", 0.5),
    "unproductive": ("Unproductive", 0.0),
}

PRODUCTIVE = "productive"
NEUTRAL = "neutral"
UNPRODUCTIVE = "unproductive"
