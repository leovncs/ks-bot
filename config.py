"""
config.py  -  Single source of truth for all shared constants.

Import this module instead of duplicating labels, colors, or slot
definitions across cogs and services.
"""

import discord

# ── Event days ────────────────────────────────────────────────────────────────

VALID_DAYS: set[int] = {1, 2, 4}

DAY_KEYS: list[str] = ["day1", "day2", "day4"]

DAY_LABELS: dict[str, str] = {
    "day1": "🏗️ Day 1 — Construction",
    "day2": "🔬 Day 2 — Research",
    "day4": "⚔️  Day 4 — Troops",
}

DAY_COLORS: dict[str, discord.Color] = {
    "day1": discord.Color.orange(),
    "day2": discord.Color.blue(),
    "day4": discord.Color.red(),
}

# Speedup type prioritised when scoring users per day
DAY_PRIORITY: dict[str, list[str]] = {
    "day1": ["construction", "general"],
    "day2": ["research",     "general"],
    "day4": ["training",     "general"],
}

# Accepts "1", "d1", "day1" etc.  →  canonical key
DAY_ALIASES: dict[str, str] = {
    "1": "day1", "d1": "day1", "day1": "day1",
    "2": "day2", "d2": "day2", "day2": "day2",
    "4": "day4", "d4": "day4", "day4": "day4",
}

# ── Slot structure ────────────────────────────────────────────────────────────
#
# Slots are 30 minutes wide, always at :15 and :45.
# Each event day starts with a special pre-reset slot at 23:45 of the
# *previous* calendar day, then continues from 00:15 through 23:45.
#
#   Day 1  [0] 23:45  ← D-1 pre-reset
#          [1] 00:15
#          ...
#          [48] 23:45 ← end of Day 1  (also the first slot of Day 2)
#
#   Day 2  [0] 23:45  ← shared with Day 1's last slot
#          [1] 00:15
#          ...
#          [48] 23:45
#
#   Day 4  same pattern as Day 1 (D3 pre-reset at index 0)

_REGULAR_SLOTS: list[str] = [
    f"{h:02d}:{m:02d}" for h in range(24) for m in (15, 45)
]

# Each day: 49 slots total  [23:45, 00:15, 00:45, ..., 23:15, 23:45]
SLOTS_PER_DAY: dict[str, list[str]] = {
    day: ["23:45"] + _REGULAR_SLOTS for day in DAY_KEYS
}

# Flat deduplicated list used for generic display (scheduler, admin preview)
ALL_SLOTS: list[str] = ["23:45"] + _REGULAR_SLOTS

# ── Speedup types ─────────────────────────────────────────────────────────────

SPEEDUP_TYPES: list[str] = [
    "general", "training", "construction", "research", "healing", "learning"
]

SPEEDUP_LABELS: dict[str, str] = {
    "general":      "⏩ General",
    "training":     "⚔️  Troops Training",
    "construction": "🏗️  Construction",
    "research":     "🔬 Research",
    "healing":      "💊 Healing",
    "learning":     "📚 Learning",
}