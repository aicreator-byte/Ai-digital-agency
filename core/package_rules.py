"""
Penentuan paket OTOMATIS — dipanggil website_agent waktu Project baru
dibuat, supaya tidak perlu klien pilih manual atau kamu assign satu-satu.

Urutan: cek kategori_paket dulu; kalau kategori tidak ada di mapping,
fallback ke score_thresholds (skor lead dari scraper_agent).
"""

from __future__ import annotations

from functools import lru_cache

import yaml

from config.settings import BASE_DIR
from core.packages import DEFAULT_PACKAGE

RULES_PATH = BASE_DIR / "config" / "package_rules.yaml"


@lru_cache
def _load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def assign_package(kategori: str | None, score: int = 0) -> str:
    rules = _load_rules()

    if kategori:
        mapped = rules.get("kategori_paket", {}).get(kategori.lower())
        if mapped:
            return mapped

    for tier in rules.get("score_thresholds", []):
        if score >= tier["min_score"]:
            return tier["paket"]

    return DEFAULT_PACKAGE
