"""
parser.py  -  Interprets availability messages for the kingdom event schedule.

Slot structure (30-minute intervals, always :15 and :45):
  Day 1:  23:45 (D-1 pre-reset) → 00:15, 00:45, ..., 23:45
  Day 2:  23:45 (shared with D1 last slot) → 00:15, 00:45, ..., 23:45
  Day 4:  23:45 (D3 pre-reset) → 00:15, 00:45, ..., 23:45

Each slot is 30 minutes wide. The 23:45 slot straddles the day boundary:
  - In Day 1: last 15 min of D1
  - In Day 2: first 15 min of D2 (same physical slot, shared)
"""

import re
import logging

logger = logging.getLogger('KingshotBot.parser')

# ── Slot definitions ──────────────────────────────────────────────────────────

VALID_DAYS = {1, 2, 4}

# 48 regular slots per day: 00:15, 00:45, 01:15, ..., 23:15, 23:45
_DAY_SLOTS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (15, 45)]

# Each day's full slot list: starts with 23:45 (pre-reset), then regular slots
# Total: 49 slots per day
SLOTS_PER_DAY: dict[str, list[str]] = {
    'day1': ['23:45'] + _DAY_SLOTS,   # 23:45 = D-1 pre-reset
    'day2': ['23:45'] + _DAY_SLOTS,   # 23:45 = shared with D1's last slot
    'day4': ['23:45'] + _DAY_SLOTS,   # 23:45 = D3 pre-reset
}

# Flat list for backward-compat (used by scheduler for display)
ALL_SLOTS = ['23:45'] + _DAY_SLOTS


# ── Snap helper ───────────────────────────────────────────────────────────────

def snap_start(hh: int, mm: int) -> str:
    """
    Floors HH:MM to the slot that contains this time (for range start).
    Slots are at :15 and :45; each covers a 30-min window.
      [hh:00 – hh:14] → hh:15  (next slot up, first slot of the window)
      [hh:15 – hh:44] → hh:15
      [hh:45 – hh:59] → hh:45
    """
    if hh == 23 and mm >= 45:
        return "23:45"
    return f"{hh:02d}:{'15' if mm < 45 else '45'}"


def snap_end(hh: int, mm: int) -> str:
    """
    Floors HH:MM to the last slot that ends at or before this time (for range end).
      [hh:00 – hh:14] → (hh-1):45  (previous slot)
      [hh:15 – hh:44] → hh:15
      [hh:45 – hh:59] → hh:45
    """
    if hh == 23 and mm >= 45:
        return "23:45"
    if mm < 15:
        prev_h = (hh - 1) % 24
        return f"{prev_h:02d}:45"
    elif mm < 45:
        return f"{hh:02d}:15"
    else:
        return f"{hh:02d}:45"


def snap_to_slot(hh: int, mm: int) -> str:
    """Alias for snap_start (used for single time snapping)."""
    return snap_start(hh, mm)


def slots_in_range(day_key: str, start: str, end: str) -> list[str]:
    """
    Returns all slots within [start, end] for the given day.

    Handles the duplicate 23:45 correctly:
      - 23:45 as start → index 0  (pre-reset slot)
      - 23:45 as end   → last index (end of day)
    """
    slot_list = SLOTS_PER_DAY.get(day_key, ALL_SLOTS)

    if start == end:
        return [start] if start in slot_list else list(slot_list)

    try:
        si = slot_list.index(start)
    except ValueError:
        return list(slot_list)

    try:
        # When end is 23:45 and start is not the pre-reset slot,
        # target the LAST 23:45 (end of day), not the first (pre-reset).
        if end == '23:45' and si > 0:
            ei = len(slot_list) - 1
        else:
            ei = slot_list.index(end)
    except ValueError:
        return list(slot_list)

    if si <= ei:
        return slot_list[si:ei+1]
    return list(slot_list)


# ── Regex patterns ────────────────────────────────────────────────────────────

_DAY_RE = re.compile(
    r'\b(?:day|dia|jour|tag|d[íi]a|giorno|den)\s*[:\-]?\s*([1-9])\b',
    re.IGNORECASE
)
_ALL_DAYS_RE = re.compile(
    r'\b(?:all\s+(?:\d+\s+)?days?|todos\s+(?:os\s+)?dias?|alle\s+tage|'
    r'tous\s+les\s+jours?|ogni\s+giorno|all\s+3\s+days?|os\s+3\s+dias?|'
    r'the\s+3\s+days?)\b',
    re.IGNORECASE
)
_RANGE_RE = re.compile(
    r'(?:'
    r'between\s+([01]?\d|2[0-3]):([0-5]\d)\s+and\s+([01]?\d|2[0-3]):([0-5]\d)'
    r'|'
    r'\b([01]?\d|2[0-3]):([0-5]\d)\s*(?:[-–—]|to|até|a|au|bis|alle)\s*([01]?\d|2[0-3]):([0-5]\d)\b'
    r')',
    re.IGNORECASE
)
_TIME_RE  = re.compile(r'\b([01]?\d|2[0-3]):([0-5]\d)\b')
_ANY_RE   = re.compile(
    r'\b(?:any\s*time|anytime|qualquer\s*hor[aá]rio?|any)\b',
    re.IGNORECASE
)
_RESET_RE = re.compile(
    r'\b(?:reset|near\s+reset|close\s+to\s+reset|midnight|'
    r'próximo\s+ao\s+reset|meia.noite)\b',
    re.IGNORECASE
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _strip_mention(text: str) -> str:
    text = re.sub(r'<@!?\d+>', '', text)
    text = re.sub(r'@\w+', '', text)
    return text.strip()


def _parse_range(m: re.Match) -> tuple[str, str]:
    # Group layout: "between...and" uses groups 1-4; standard "-/to" uses groups 5-8
    if m.group(1) is not None:
        start = snap_start(int(m.group(1)), int(m.group(2)))
        end   = snap_end(int(m.group(3)),   int(m.group(4)))
    else:
        start = snap_start(int(m.group(5)), int(m.group(6)))
        end   = snap_end(int(m.group(7)),   int(m.group(8)))
    return start, end


def _associate_to_days(text: str, days: set[int]) -> dict[str, list[tuple[str, str]]]:
    """
    Finds time ranges near each explicit day mention and associates them.
    Returns { 'day1': [(start, end), ...], ... }
    """
    result: dict[str, list[tuple[str, str]]] = {}

    # Positions of each valid day mention in the text
    positions: list[tuple[int, int]] = []
    for m in _DAY_RE.finditer(text):
        d = int(m.group(1))
        if d in days:
            positions.append((m.start(), d))
    positions.sort()

    for i, (pos, day_num) in enumerate(positions):
        next_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        segment  = text[pos:next_pos]
        key      = f"day{day_num}"
        ranges: list[tuple[str, str]] = []

        for rm in _RANGE_RE.finditer(segment):
            ranges.append(_parse_range(rm))

        if not ranges:
            # Try a single time → build a 1-hour (2-slot) window
            used = {idx for rm in _RANGE_RE.finditer(segment)
                    for idx in range(rm.start(), rm.end())}
            for tm in _TIME_RE.finditer(segment):
                if tm.start() not in used:
                    slot = snap_start(int(tm.group(1)), int(tm.group(2)))
                    sl   = SLOTS_PER_DAY[key]
                    try:
                        idx     = sl.index(slot)
                        end_idx = min(len(sl) - 1, idx + 2)  # +1h window
                        ranges.append((sl[idx], sl[end_idx]))
                    except ValueError:
                        pass
                    break

        if ranges:
            result[key] = ranges

    return result


# ── Public API ────────────────────────────────────────────────────────────────

def parse_availability(message: str) -> dict[str, list[tuple[str, str]]]:
    """
    Parses a free-form availability message.

    Returns:
    {
        'day1': [('23:45', '02:15')],        # list of (start, end) slot ranges
        'day2': [('any', 'any')],            # any time
        'day4': [('21:15', '23:45')],
    }

    The 23:45 slot has special meaning per day:
      day1/day4: pre-reset slot (D-1 or D3 evening)
      day2:      shared with day1's last slot (first 15min of D2)
    """
    text = _strip_mention(message)

    wants_all = bool(_ALL_DAYS_RE.search(text))
    mentioned = {int(m.group(1)) for m in _DAY_RE.finditer(text)
                 if int(m.group(1)) in VALID_DAYS}

    if wants_all and not mentioned:
        mentioned = set(VALID_DAYS)
    if not mentioned:
        mentioned = set(VALID_DAYS)

    # Global ranges (not tied to a specific day mention)
    global_ranges = [_parse_range(m) for m in _RANGE_RE.finditer(text)]

    wants_any        = bool(_ANY_RE.search(text))
    wants_near_reset = bool(_RESET_RE.search(text))

    day_assoc = _associate_to_days(text, mentioned)
    result: dict[str, list[tuple[str, str]]] = {}

    for day in sorted(mentioned):
        key = f"day{day}"

        if key in day_assoc and day_assoc[key]:
            result[key] = day_assoc[key]

        elif global_ranges:
            result[key] = global_ranges

        elif wants_near_reset:
            # Near reset: last 2 slots of day + first slot of next = 23:15, 23:45, 00:15
            sl = SLOTS_PER_DAY[key]
            result[key] = [('23:15', '00:15')]   # scheduler will handle via slots_in_range

        elif wants_any:
            result[key] = [('any', 'any')]

        else:
            result[key] = [('any', 'any')]

    return result


def format_availability(availability: dict) -> str:
    """Formats the availability dict for a Discord embed field."""
    day_labels = {
        'day1': '🏗️  **Day 1** (Construction)',
        'day2': '🔬 **Day 2** (Research)',
        'day4': '⚔️  **Day 4** (Troops)',
    }
    lines = []
    for key, label in day_labels.items():
        if key not in availability:
            continue
        ranges = availability[key]
        if ranges == [('any', 'any')]:
            lines.append(f"  {label}: `Any time`")
        else:
            ranges_str = ', '.join(f"`{s} – {e}`" for s, e in ranges)
            lines.append(f"  {label}: {ranges_str}")
    return '\n'.join(lines) if lines else '  _(no availability detected)_'