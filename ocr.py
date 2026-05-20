"""
ocr.py  -  Extracts speedups from Kingshot / Whiteout Survival screenshots via Tesseract.

Supports all 3 display modes the game uses (toggled by Day/Hrs/Min checkboxes):
  - Days mode:    "76 day(s)7 hr(s)29 min(s)"
  - Hours mode:   "1,831 hr(s)29 min(s)"
  - Minutes mode: "109,889 min(s)"

All values are normalised to the "XdYhZm" format (e.g. "76d7h29m").

Strategy: split the panel image into left (item names) and right (values) columns,
run OCR independently on each, then zip by ordinal index.
"""

import re
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger('KingshotBot.ocr')


# ── Tesseract setup ───────────────────────────────────────────────────────────

def _configure_tesseract():
    """
    Locates the Tesseract binary.
    Priority: TESSERACT_PATH env var → system PATH → common Windows install dirs.
    """
    import sys, os, pytesseract

    env_path = os.getenv('TESSERACT_PATH', '').strip()
    if env_path:
        pytesseract.pytesseract.tesseract_cmd = env_path
        logger.info(f"Tesseract set via TESSERACT_PATH: {env_path}")
        return

    try:
        pytesseract.get_tesseract_version()
        return
    except Exception:
        pass

    if sys.platform != 'win32':
        logger.error("Tesseract not found in PATH. Install: sudo apt install tesseract-ocr")
        return

    candidates = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'),
        r'C:\tools\Tesseract-OCR\tesseract.exe',
    ]
    for path in candidates:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"Tesseract found at: {path}")
            return

    logger.error(
        "Tesseract not found!\n"
        "  Option 1: Add to Windows PATH and restart terminal\n"
        "  Option 2: Set in .env: TESSERACT_PATH=C:\\Program Files\\Tesseract-OCR\\tesseract.exe\n"
        "  Download: https://github.com/UB-Mannheim/tesseract/wiki"
    )


# ── Item name keywords (English only) ────────────────────────────────────────

SPEEDUP_KEYWORDS: dict[str, list[str]] = {
    'general':      ['general speedup', 'general'],
    'training':     ['soldier training speedup', 'soldier training', 'training speedup', 'training'],
    'construction': ['construction speedup', 'construction'],
    'research':     ['research speedup', 'research'],
    'healing':      ['soldier healing speedup', 'soldier healing', 'healing speedup', 'healing'],
    'learning':     ['learning speedups', 'learning speedup', 'learning'],
}


# ── OCR noise fixes ───────────────────────────────────────────────────────────

def _fix_ocr(text: str) -> str:
    """Fixes common Tesseract misreads on this game's font."""
    text = re.sub(r'(?<=\d)S(?=\d)', '5', text)      # digit-S-digit  → 5
    text = re.sub(r'(?<=\(s\))I(?=\d)', '1', text)   # (s)I6 → (s)16
    text = re.sub(r'\bI(?=\d)', '1', text)             # leading I → 1
    return text


# ── Time conversion helpers ───────────────────────────────────────────────────

def _parse_num(s: str) -> int:
    """Strips thousands-separator commas and returns int."""
    return int(s.replace(',', ''))

def _dhm(total_minutes: int) -> str:
    """Converts a total-minute count to 'XdYhZm' string."""
    d, rem = divmod(total_minutes, 24 * 60)
    h, m   = divmod(rem, 60)
    parts  = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    return ''.join(parts) or "0m"


# ── Single-line time parser ───────────────────────────────────────────────────

def _extract_time(text: str) -> Optional[str]:
    """
    Parses one time string in any of the three game display modes and
    returns a normalised 'XdYhZm' string, or None if nothing matched.

    Handles thousands commas (e.g. "1,831"), merged min-on-next-line OCR
    artefacts, and partial values (e.g. hr(s) without min).
    """
    # --- Mode 1: days ---
    # "76 day(s)7 hr(s)29 min(s)"  or  "1 day(s)16 hr(s)"
    m = re.search(
        r'([\d,]+)\s*day\(s\)'
        r'(?:\s*([\d,]+)\s*hr\(s\))?'
        r'(?:\s*([\d,]+)\s*min\(s\))?',
        text, re.IGNORECASE
    )
    if m:
        d  = _parse_num(m.group(1))
        h  = _parse_num(m.group(2)) if m.group(2) else 0
        mn = _parse_num(m.group(3)) if m.group(3) else 0
        return _dhm(d * 1440 + h * 60 + mn)

    # --- Mode 2: hours only ---
    # "1,831 hr(s)29 min(s)"  or  "40 hr(s)"
    m = re.search(
        r'([\d,]+)\s*hr\(s\)(?:\s*([\d,]+)\s*min\(s\))?',
        text, re.IGNORECASE
    )
    if m:
        h  = _parse_num(m.group(1))
        mn = _parse_num(m.group(2)) if m.group(2) else 0
        return _dhm(h * 60 + mn)

    # --- Mode 3: minutes only ---
    # "109,889 min(s)"
    m = re.search(r'([\d,]+)\s*min\(s\)', text, re.IGNORECASE)
    if m:
        return _dhm(_parse_num(m.group(1)))

    return None


# ── Column parsers ────────────────────────────────────────────────────────────

def _extract_names_ordered(left_text: str) -> list[str]:
    """
    Identifies speedup types from the left column in top-to-bottom order.
    Returns a list of stype strings (e.g. ['general', 'training', ...]).
    """
    text = _fix_ocr(left_text).lower()
    found: list[tuple[int, str]] = []

    for stype, keywords in SPEEDUP_KEYWORDS.items():
        for kw in keywords:
            idx = text.find(kw)
            if idx != -1:
                found.append((idx, stype))
                break

    found.sort()
    seen: set[str] = set()
    result: list[str] = []
    for _, stype in found:
        if stype not in seen:
            seen.add(stype)
            result.append(stype)
    return result


def _extract_values_ordered(right_text: str) -> list[str]:
    """
    Extracts all time values from the right column in top-to-bottom order.

    Handles the common OCR split where a line ends with a bare number and
    the next line starts with 'min(s)' (game wraps long values).
    """
    text = _fix_ocr(right_text)

    # Fix split lines: "52\nmin(s)" → "52 min(s)"
    text = re.sub(r'(\d)\s*\n\s*min\(s\)', r'\1 min(s)', text, flags=re.IGNORECASE)

    # Split into lines and try to parse each one
    values: list[str] = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        # If this line has no time unit word, peek at the next line and merge
        if i + 1 < len(lines) and not re.search(r'day\(s\)|hr\(s\)|min\(s\)', line, re.I):
            merged = line + ' ' + lines[i + 1]
            val = _extract_time(merged)
            if val:
                values.append(val)
                i += 2
                continue
        val = _extract_time(line)
        if val:
            values.append(val)
        i += 1

    return values


# ── Main OCR entry point ──────────────────────────────────────────────────────

async def extract_speedups_from_image(image_bytes: bytes) -> dict:
    """
    Extracts speedup values from a screenshot buffer.

    Crops the panel area, splits into left/right columns, runs Tesseract
    on each independently, then zips names with values by position.
    """
    try:
        import pytesseract
        import cv2
        import numpy as np

        _configure_tesseract()

        img_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("Could not decode image")
            return {}

        h, w = img.shape[:2]
        logger.info(f"Image: {w}x{h}px")

        # Crop the dialog panel and upscale for better OCR accuracy
        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        panel = gray[int(h * 0.24): int(h * 0.90), int(w * 0.01): int(w * 0.99)]
        panel = cv2.resize(panel, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, thresh = cv2.threshold(panel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        ph, pw = thresh.shape
        left_img  = thresh[:, :pw // 2]
        right_img = thresh[:, pw // 2:]

        cfg = '--psm 6 --oem 3'
        left_text  = pytesseract.image_to_string(left_img,  lang='eng', config=cfg)
        right_text = pytesseract.image_to_string(right_img, lang='eng', config=cfg)

        logger.debug(f"Left OCR:\n{left_text}")
        logger.debug(f"Right OCR:\n{right_text}")

        names  = _extract_names_ordered(left_text)
        values = _extract_values_ordered(right_text)

        logger.info(f"Names  ({len(names)}):  {names}")
        logger.info(f"Values ({len(values)}): {values}")

        result = dict(zip(names, values))
        logger.info(f"Extracted: {result}")
        return result

    except ImportError as e:
        logger.error(f"Missing dependency: {e}. Run: pip install pytesseract opencv-python-headless")
        return {}
    except Exception as e:
        logger.error(f"Unexpected OCR error: {e}", exc_info=True)
        return {}


# ── Image download ────────────────────────────────────────────────────────────

async def download_image(url: str) -> Optional[bytes]:
    """Downloads an image from a Discord CDN URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.error(f"HTTP {resp.status} downloading image")
    except Exception as e:
        logger.error(f"Image download failed: {e}")
    return None


# ── Discord formatting ────────────────────────────────────────────────────────

def format_speedups(speedups: dict) -> str:
    """Formats the speedup dict for a Discord embed field."""
    from config import SPEEDUP_LABELS
    lines = [f"  {label}: `{speedups[key]}`"
             for key, label in SPEEDUP_LABELS.items() if key in speedups]
    return '\n'.join(lines) if lines else '  _(No speedups detected)_'