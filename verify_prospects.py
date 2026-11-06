#!/usr/bin/env python3
"""Verifikasi website + enrichment kontak untuk 81 prospek agency (status='scored').

READ-ONLY terhadap DB. Hasil ditulis ke file JSON laporan, TIDAK ke agency.db.
Penulisan ke DB butuh persetujuan Di (main agent) setelah laporan direview.

Metode:
  1. Ambil tag OSM (phone, website, contact:*) untuk node/way tiap prospek via Overpass.
  2. HEAD-check tiap URL website yang ditemukan (konfirmasi situs benar-benar hidup).
  3. Tandai kandidat yang ternyata sudah punya website (bukan prospek paket website,
     tapi kandidat paket chatbot) vs yang benar-benar belum punya.

Jalankan dari network yang bisa mencapai overpass-api.de
(sandbox riset 2026-10-15: 403 via proxy).

Contoh:
  python3 verify_prospects.py --db storage/agency.db --out /tmp/prospect_verify.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET

OSM_RE = re.compile(r"openstreetmap\.org/(node|way)/(\d+)")
OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_API = "https://www.openstreetmap.org/api/0.6"
CONTACT_KEYS = ("phone", "contact:phone", "contact:mobile", "contact:whatsapp",
                "website", "contact:website", "contact:email")


def load_scored(db_path: str):
    c = sqlite3.connect(db_path)
    biz = {r[0]: json.loads(r[1]) for r in c.execute("SELECT id, data FROM businesses")}
    leads = [json.loads(r[0]) for r in c.execute("SELECT data FROM leads")]
    out = []
    for l in leads:
        if l.get("status") != "scored":
            continue
        b = biz.get(l["business_id"], {})
        m = OSM_RE.search(b.get("google_maps_url") or "")
        out.append({
            "business_id": l["business_id"],
            "nama": b.get("nama"), "lokasi": b.get("lokasi"),
            "kategori": b.get("kategori"),
            "nomor_wa_db": b.get("nomor_wa") or "",
            "has_website_db": bool(b.get("has_website")),
            "osm_type": m.group(1) if m else None,
            "osm_id": m.group(2) if m else None,
        })
    return out


def overpass_tags(items, batch=40):
    """Return {(type, id): tags} — batched, read-only.

    Mencoba Overpass dulu; bila 403 (egress VM), fallback ke OSM API resmi
    per-objek (terbukti 200 dari network ini).
    """
    try:
        return _overpass_tags(items, batch)
    except Exception as e:  # noqa: BLE001 - 403 dsb -> fallback
        print(f"overpass gagal ({type(e).__name__}), fallback ke OSM API")
        return _osm_api_tags(items)


def _overpass_tags(items, batch=40):
    objs = [(i["osm_type"], i["osm_id"]) for i in items if i["osm_id"]]
    for k in range(0, len(objs), batch):
        chunk = objs[k:k + batch]
        nodes = ",".join(i for t, i in chunk if t == "node")
        ways = ",".join(i for t, i in chunk if t == "way")
        parts = []
        if nodes:
            parts.append(f"node(id:{nodes});")
        if ways:
            parts.append(f"way(id:{ways});")
        ql = f"[out:json][timeout:60];({''.join(parts)});out tags;"
        req = urllib.request.Request(
            OVERPASS, data=ql.encode(),
            headers={"User-Agent": "agency-prospect-verify/1.0"})
        with urllib.request.urlopen(req, timeout=70) as r:
            data = json.loads(r.read())
        for el in data.get("elements", []):
            result[(el["type"], str(el["id"]))] = el.get("tags", {})
    return result


def _osm_api_tags(items):
    """Ambil tag per objek via OSM API resmi (satu request per objek)."""
    result = {}
    for it in items:
        t, oid = it["osm_type"], it["osm_id"]
        if not oid:
            continue
        try:
            req = urllib.request.Request(
                f"{OSM_API}/{t}/{oid}",
                headers={"User-Agent": "agency-prospect-verify/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                root = ET.fromstring(r.read())
            tags = {tag.get("k"): tag.get("v") for tag in root.iter("tag")}
            result[(t, oid)] = tags
        except Exception as e:  # noqa: BLE001 - catat, lanjut
            print(f"  OSM API {t}/{oid} gagal: {type(e).__name__}")
        time.sleep(0.3)  # sopan ke OSM API
    return result


def head_ok(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url, method=method,
                headers={"User-Agent": "agency-prospect-verify/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status < 400:
                    return f"live:{r.status}"
        except Exception as e:  # noqa: BLE001 - catat alasan gagal, lanjut
            last = f"{type(e).__name__}"
    return f"dead:{last}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="storage/agency.db")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0 = semua")
    args = ap.parse_args()

    items = load_scored(args.db)
    if args.limit:
        items = items[:args.limit]
    print(f"prospek scored: {len(items)}")

    tags = overpass_tags(items)
    print(f"tag OSM didapat: {len(tags)}")

    report = []
    for it in items:
        t = tags.get((it["osm_type"], it["osm_id"]), {})
        contact = {k: t[k] for k in CONTACT_KEYS if t.get(k)}
        web = contact.get("website") or contact.get("contact:website") or ""
        web_status = head_ok(web) if web else "none"
        report.append({
            **it,
            "osm_contact_tags": contact,
            "website_osm": web,
            "website_status": web_status,
            "flag_koreksi": (
                "SUDAH_PUNYA_WEB" if web_status.startswith("live")
                else "PERLU_CEK_MANUAL" if not web else "WEB_MATI"
            ),
        })

    with open(args.out, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    live = sum(1 for r in report if r["website_status"].startswith("live"))
    withwa = sum(1 for r in report if any("phone" in k or "whatsapp" in k
                                          for k in r["osm_contact_tags"]))
    print(f"website live: {live}/{len(report)} | tag telepon/WA: {withwa}/{len(report)}")
    print(f"laporan: {args.out}")


if __name__ == "__main__":
    main()
