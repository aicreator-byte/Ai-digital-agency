"""
Klien WhatsApp: kirim teks/gambar lewat bridge lokal (whatsapp/bridge.js).

Pengaman anti-banned (nomor khusus jualan, tetap hati-hati):
- Batas harian untuk pesan DINGIN (ke orang yang belum pernah chat) -> WA_DAILY_LIMIT.
- Jeda acak antar pesan, bukan kirim beruntun.
- Balasan ke orang yang chat duluan tidak dihitung ke batas harian.

Kalau WA_ENABLED=false (default), semua pesan cuma di-log (mode stub).
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import date
from pathlib import Path

import requests

from config.settings import (
    BASE_DIR,
    STORAGE_DIR,
    WA_BRIDGE_TOKEN,
    WA_BRIDGE_URL,
    WA_COLD_DELAY,
    WA_DAILY_LIMIT,
    WA_ENABLED,
    WA_REPLY_DELAY,
)

logger = logging.getLogger("whatsapp")

_COUNTER_FILE = STORAGE_DIR / "wa_daily.json"


def normalize_number(raw: str | None) -> str | None:
    """'0812-3456-789' / '+62 812...' -> '62812...'. None kalau tidak valid."""
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not digits.startswith("62") or not (10 <= len(digits) <= 15):
        return None
    return digits


def _read_counter() -> dict:
    try:
        data = json.loads(_COUNTER_FILE.read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    if data.get("date") != date.today().isoformat():
        data = {"date": date.today().isoformat(), "count": 0}
    return data


def cold_sent_today() -> int:
    return _read_counter()["count"]


def _bump_counter() -> None:
    data = _read_counter()
    data["count"] += 1
    _COUNTER_FILE.write_text(json.dumps(data))


def _post(path: str, payload: dict) -> bool:
    try:
        resp = requests.post(
            f"{WA_BRIDGE_URL}{path}", json=payload,
            headers={"x-token": WA_BRIDGE_TOKEN}, timeout=60,
        )
    except requests.RequestException as exc:
        logger.error("Bridge WA tidak terjangkau: %s", exc)
        return False
    if resp.status_code != 200:
        logger.error("Kirim WA gagal (%s): %s", resp.status_code, resp.text[:200])
        return False
    return True


def _prepare(number_raw: str | None, cold: bool) -> str | None:
    """Validasi nomor, cek batas harian, kasih jeda. Return nomor siap kirim atau None."""
    number = normalize_number(number_raw)
    if number is None:
        logger.warning("Nomor WA tidak valid: %r", number_raw)
        return None
    if cold and cold_sent_today() >= WA_DAILY_LIMIT:
        logger.warning("Batas harian pesan dingin (%s) tercapai, kirim ditunda.", WA_DAILY_LIMIT)
        return None
    low, high = WA_COLD_DELAY if cold else WA_REPLY_DELAY
    time.sleep(random.uniform(low, high))
    return number


def send_text(number_raw: str | None, text: str, cold: bool = False) -> bool:
    if not WA_ENABLED:
        logger.info("[STUB WA] ke %s: %s", number_raw, text)
        return True
    number = _prepare(number_raw, cold)
    if number is None:
        return False
    ok = _post("/send", {"to": number, "text": text})
    if ok and cold:
        _bump_counter()
    return ok


def send_image(number_raw: str | None, image_path: str, caption: str = "", cold: bool = False) -> bool:
    if not WA_ENABLED:
        logger.info("[STUB WA GAMBAR] ke %s: %s (%s)", number_raw, image_path, caption)
        return True
    number = _prepare(number_raw, cold)
    if number is None:
        return False
    path = Path(image_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    return _post("/send-image", {"to": number, "image_path": str(path), "caption": caption})
