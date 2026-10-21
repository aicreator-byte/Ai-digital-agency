#!/usr/bin/env python3
"""Prospek pagi agency: cari lead baru via OSM/Overpass (tanpa API key).

Membaca target dari prospect_targets.yaml (kategori + lokasi), memanggil
agents.scraper_agent.find_leads untuk tiap target, dan menulis hasilnya ke
out/leads-YYYY-MM-DD.json. File ini dipakai sebagai artifact Actions, BUKAN
di-commit ke repo (DB dan data bisnis tidak boleh masuk repo).

Jalankan: python3 scripts/daily_prospects.py
Env: SCRAPER_BACKEND=osm (default di config), KATEGORI/LOKASI untuk override
satu target.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from agents.scraper_agent import find_leads  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def load_targets() -> list[dict]:
    override_cat = os.getenv("KATEGORI")
    override_loc = os.getenv("LOKASI")
    if override_cat and override_loc:
        return [{"kategori": override_cat, "lokasi": override_loc}]
    with open(ROOT / "prospect_targets.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("targets", [])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    all_leads: list[dict] = []
    for t in load_targets():
        kategori, lokasi = t["kategori"], t["lokasi"]
        print(f"[prospek] {kategori} @ {lokasi} ...", flush=True)
        try:
            leads = find_leads(kategori, lokasi)
        except Exception as exc:  # satu target gagal != semua gagal
            print(f"[prospek] GAGAL {kategori} @ {lokasi}: {exc}", flush=True)
            continue
        print(f"[prospek] dapat {len(leads)} lead", flush=True)
        for lead in leads:
            d = lead.model_dump(mode="json")
            d["target_kategori"] = kategori
            d["target_lokasi"] = lokasi
            all_leads.append(d)
    out_file = OUT / f"leads-{date.today().isoformat()}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, ensure_ascii=False, indent=2)
    print(f"[prospek] total {len(all_leads)} lead -> {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
