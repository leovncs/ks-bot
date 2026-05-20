"""
database.py  -  JSON-backed state persistence.

All bot state lives in data/state.json.  Every public function loads,
mutates (if needed), and saves atomically under a threading lock so the
bot is safe to run in a single process with concurrent async tasks.
"""

import json
import os
import threading
from datetime import datetime, timezone
from typing import Optional

_DATA_FILE = "data/state.json"
_lock      = threading.Lock()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _default() -> dict:
    return {
        # ── Event flow ─────────────────────────────────────────────────────
        "accepting_submissions": True,
        "submissions":           {},      # str(user_id) → submission dict
        "schedule":              {},      # day_key → list[entry]

        # ── Channel IDs ────────────────────────────────────────────────────
        "channel_submissions":   None,    # where members send their signup
        "channel_admin":         None,    # where admins run commands
        "channel_announcements": None,    # where schedule is published
        "channel_lookup":        None,    # where members run !myschedule

        # ── Channel visibility ─────────────────────────────────────────────
        "lookup_open": False,             # True when #my-schedule is visible
    }


def _load() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(_DATA_FILE):
        return _default()
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Back-fill any keys added after initial creation
    defaults = _default()
    for key, val in defaults.items():
        data.setdefault(key, val)
    return data


def _save(state: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _patch(**fields) -> None:
    """Load → update fields → save, all under the lock."""
    with _lock:
        s = _load()
        s.update(fields)
        _save(s)


# ── Read-only accessors ───────────────────────────────────────────────────────

def get_state() -> dict:
    with _lock:
        return _load()

def is_accepting() -> bool:
    return _load()["accepting_submissions"]

def get_channel(name: str) -> Optional[int]:
    """
    Returns the stored channel ID for the given name.
    Valid names: 'submissions', 'admin', 'announcements', 'lookup'.
    """
    return _load().get(f"channel_{name}")

def is_lookup_open() -> bool:
    return _load().get("lookup_open", False)

def get_all_submissions() -> dict:
    return _load()["submissions"]

def get_submission(user_id: int) -> Optional[dict]:
    return _load()["submissions"].get(str(user_id))

def get_schedule() -> dict:
    return _load()["schedule"]


# ── Write accessors ───────────────────────────────────────────────────────────

def set_accepting(value: bool) -> None:
    _patch(accepting_submissions=value)

def set_channel(name: str, channel_id: int) -> None:
    _patch(**{f"channel_{name}": channel_id})

def set_lookup_open(value: bool) -> None:
    _patch(lookup_open=value)

def save_submission(
    user_id: int,
    username: str,
    speedups: dict,
    availability: dict,
) -> None:
    with _lock:
        s = _load()
        s["submissions"][str(user_id)] = {
            "user_id":      user_id,
            "username":     username,
            "speedups":     speedups,
            "availability": availability,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(s)

def remove_submission(user_id: int) -> bool:
    """Remove a submission by user ID. Returns True if it existed."""
    with _lock:
        s = _load()
        existed = str(user_id) in s["submissions"]
        s["submissions"].pop(str(user_id), None)
        _save(s)
    return existed

def save_schedule(schedule: dict) -> None:
    _patch(schedule=schedule)

def reset_all() -> None:
    with _lock:
        _save(_default())