#!/usr/bin/env python3
"""Draf follow-up sore agency: HANYA menyiapkan draf, TIDAK mengirim.

Mengambil lead hasil scrape (find_leads per target), menyaring yang TANPA
website (kandidat paket website — prospek yang sudah punya website adalah
kandidat paket chatbot, bukan paket website), lalu menulis draf pesan
follow-up per lead ke out/followup-drafts-YYYY-MM-DD.md.

Draf ini untuk direview Di / Hermes sebelum dikirim manual. Pengiriman WA
tidak pernah otomatis dari workflow ini (bridge WA mati + butuh persetujuan
per pesan).

Jalankan: python3 scripts/followup_drafts.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from agents.scraper_agent import find_leads  # noqa: E402
from core.database import get_business  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def load_targets() -> list[dict]:
    with open(ROOT / "prospect_targets.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("targets", [])


def draft_for(nama: str, kategori: str, lokasi: str) -> str:
    return (
        f"Halo {nama}, saya dari JasaBikin. Kami bantu {kategori} di {lokasi} "
        f"punya website profesional (mulai Rp2,5jt) + chatbot WA opsional. "
        f"Boleh saya kirim contoh demo gratis untuk usaha Anda?"
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [f"# Draf Follow-up {date.today().isoformat()}", "",
             "_DRAF SAJA — jangan kirim otomatis. Review dulu._", ""]
    count = 0
    for t in load_targets():
        kategori, lokasi = t["kategori"], t["lokasi"]
        try:
            leads = find_leads(kategori, lokasi)
        except Exception as exc:
            print(f"[followup] GAGAL {kategori} @ {lokasi}: {exc}", flush=True)
            continue
        for lead in leads:
            d = lead.model_dump(mode="json")
            biz = get_business(lead.business_id)
            if biz:
                d["business"] = biz.model_dump(mode="json")
            # Kandidat paket website = yang belum punya website.
            biz_data = d.get("business", {})
            if biz_data.get("has_website"):
                continue
            nama = biz_data.get("nama") or "(tanpa nama)"
            lines.append(f"## {nama} ({kategori}, {lokasi})")
            lines.append("")
            lines.append(draft_for(nama, kategori, lokasi))
            lines.append("")
            count += 1
    out_file = OUT / f"followup-drafts-{date.today().isoformat()}.md"
    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"[followup] {count} draf -> {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
