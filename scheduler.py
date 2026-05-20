"""
scheduler.py  -  Generates the speedup schedule allocating users to 30-min slots.

Slot structure per day (49 slots each):
  [0]    23:45  ← pre-reset slot (D-1 for Day1/Day4; shared D1 last for Day2)
  [1]    00:15
  [2]    00:45
  ...
  [48]   23:45  ← end-of-day slot

Priority:
  Day 1 (Construction) → construction > general
  Day 2 (Research)     → research     > general
  Day 4 (Troops)       → training     > general
"""

import re
import logging
from typing import Optional

from config import SLOTS_PER_DAY
from parser import slots_in_range

logger = logging.getLogger('KingshotBot.scheduler')

DAY_PRIORITY: dict[str, list[str]] = {
    'day1': ['construction', 'general'],
    'day2': ['research',     'general'],
    'day4': ['training',     'general'],
}

DAY_LABELS: dict[str, str] = {
    'day1': '🏗️ Day 1 — Construction',
    'day2': '🔬 Day 2 — Research',
    'day4': '⚔️  Day 4 — Troops',
}

DAY_NOTES: dict[str, str] = {
    'day1': ('`23:45` = D-1 pre-reset slot (15 min before Day 1 begins)\n'
             '`23:45`★ = last slot of Day 1 (also first 15 min of Day 2)'),
    'day2': ('`23:45` = shared slot — last 15 min of Day 1 + first 15 min of Day 2'),
    'day4': ('`23:45` = D3 pre-reset slot (15 min before Day 4 begins)'),
}


# ── Time conversion ───────────────────────────────────────────────────────────

def _to_minutes(time_str: Optional[str]) -> int:
    """Converts 'XdYhZm' speedup string to total minutes."""
    if not time_str:
        return 0
    total = 0
    for pattern, factor in ((r'(\d+)d', 1440), (r'(\d+)h', 60), (r'(\d+)m', 1)):
        m = re.search(pattern, time_str)
        if m:
            total += int(m.group(1)) * factor
    return total


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(speedups: dict, day_key: str) -> int:
    for key in DAY_PRIORITY.get(day_key, ['general']):
        val = speedups.get(key)
        if val:
            return _to_minutes(val)
    return 0


# ── Slot resolution ───────────────────────────────────────────────────────────

def _available_slots(availability: dict, day_key: str) -> list[str]:
    """
    Returns the ordered list of slots the user can be assigned to on this day.
    Uses the day-specific slot list so 23:45 resolves correctly.
    """
    ranges = availability.get(day_key, [])
    if not ranges:
        return []
    if ranges == [('any', 'any')]:
        return list(SLOTS_PER_DAY[day_key])

    seen:   set[str]  = set()
    result: list[str] = []
    for start, end in ranges:
        for slot in slots_in_range(day_key, start, end):
            if slot not in seen:
                seen.add(slot)
                result.append(slot)

    # Preserve the canonical day order
    _sl = SLOTS_PER_DAY[day_key]
    order: dict[str, int] = {}
    for _i, _s in enumerate(_sl):
        if _s not in order:
            order[_s] = _i  # keep first occurrence so 23:45 sorts as pre-reset (index 0)
    result.sort(key=lambda s: order.get(s, 9999))
    return result


# ── Schedule generation ───────────────────────────────────────────────────────

def generate_schedule(submissions: dict) -> dict:
    """
    Allocates users to slots and returns:
    {
        'day1': [{'slot': '23:45', 'user_id': ..., 'username': ..., 'score': ...}, ...],
        'day2': [...],
        'day4': [...],
    }
    Users with more relevant speedup minutes are allocated first.
    If their preferred window is full, they get the first globally free slot.
    """
    schedule: dict[str, list[dict]] = {}

    for day_key in ('day1', 'day2', 'day4'):
        candidates = []
        for uid, sub in submissions.items():
            avail = sub.get('availability', {})
            if day_key not in avail or not avail[day_key]:
                continue
            candidates.append({
                'user_id':  sub['user_id'],
                'username': sub['username'],
                'score':    _score(sub.get('speedups', {}), day_key),
                'slots':    _available_slots(avail, day_key),
            })

        # Highest speedup goes first
        candidates.sort(key=lambda x: x['score'], reverse=True)

        occupied:      dict[str, dict] = {}
        day_schedule:  list[dict]      = []

        for user in candidates:
            assigned = next((s for s in user['slots'] if s not in occupied), None)

            if assigned is None:
                # Fallback: first free slot in the full day list
                assigned = next(
                    (s for s in SLOTS_PER_DAY[day_key] if s not in occupied), None
                )
                outside = True
            else:
                outside = False

            if assigned:
                occupied[assigned] = user
                entry = {
                    'slot':     assigned,
                    'user_id':  user['user_id'],
                    'username': user['username'],
                    'score':    user['score'],
                }
                if outside:
                    entry['outside_preference'] = True
                day_schedule.append(entry)
            else:
                logger.warning(f"No free slots left for {user['username']} on {day_key}")

        # Sort by canonical slot order
        _sl2 = SLOTS_PER_DAY[day_key]
        order2: dict[str, int] = {}
        for _i, _s in enumerate(_sl2):
            if _s not in order2:
                order2[_s] = _i  # keep first occurrence (23:45 pre-reset = index 0)
        day_schedule.sort(key=lambda e: order2.get(e['slot'], 9999))
        schedule[day_key] = day_schedule

    return schedule


# ── Formatting ────────────────────────────────────────────────────────────────

def format_schedule_day(day_key: str, entries: list) -> str:
    """Formats one day of the schedule for Discord, with slot annotations."""
    label = DAY_LABELS.get(day_key, day_key)
    lines = [f"**{label}**"]

    if not entries:
        lines.append("  _No users allocated._")
        return '\n'.join(lines)

    slot_list = SLOTS_PER_DAY[day_key]

    for entry in entries:
        slot  = entry['slot']
        warn  = " ⚠️" if entry.get('outside_preference') else ""
        annot = ""

        # Annotate the special 23:45 slots
        if slot == '23:45':
            idx = next((i for i, s in enumerate(slot_list) if s == slot and
                        entries.index(entry) == entries.index(
                            next(e for e in entries if e['slot'] == slot))), 0)
            if day_key in ('day1', 'day4'):
                # First entry at 23:45 is always the pre-reset slot
                if entries[0]['slot'] == '23:45' and entry is entries[0]:
                    annot = " _(pre-reset)_"
                else:
                    annot = " _(end of day)_"
            elif day_key == 'day2':
                annot = " _(shared D1→D2)_"

        lines.append(f"  `{slot}`{annot} → **{entry['username']}**{warn}")

    return '\n'.join(lines)


def format_full_schedule(schedule: dict) -> list[str]:
    """Returns one formatted string per day for Discord."""
    return [
        format_schedule_day(day_key, schedule.get(day_key, []))
        for day_key in ('day1', 'day2', 'day4')
    ]