#!/usr/bin/env python3
"""Build website agency on-demand (workflow_dispatch).

Versi pertama: menghasilkan paket file website dari template Jinja yang ada
di templates/site (bila tersedia di repo) ATAU kerangka statis minimal bila
template belum ikut. Output: out/<business>-<package>/index.html (+ aset)
siap di-zip sebagai artifact Actions.

Deploy ke Cloudflare Pages TIDAK dilakukan script ini — langkah deploy ada
di workflow (opsional, butuh secret CLOUDFLARE_API_TOKEN).

Jalankan: python3 scripts/build_website.py --business "Nama Usaha" --package W1
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

PACKAGES = {
    "W1": {"harga": "Rp2,5jt", "halaman": ["Beranda", "Layanan", "Kontak"]},
    "W2": {"harga": "Rp4,9jt", "halaman": ["Beranda", "Layanan", "Galeri", "Testimoni", "Kontak"]},
    "W3": {"harga": "Rp7,5jt", "halaman": ["Beranda", "Layanan", "Galeri", "Testimoni", "Blog", "Kontak"]},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--business", required=True)
    ap.add_argument("--package", default="W1", choices=list(PACKAGES))
    args = ap.parse_args()

    pkg = PACKAGES[args.package]
    dest = OUT / f"{args.business}-{args.package}"
    dest.mkdir(parents=True, exist_ok=True)

    template_dir = ROOT / "templates" / "site"
    if template_dir.exists():
        shutil.copytree(template_dir, dest, dirs_exist_ok=True)
        print(f"[build] template disalin dari {template_dir}")
    else:
        items = "".join(f"<li>{h}</li>" for h in pkg["halaman"])
        (dest / "index.html").write_text(
            f"<!doctype html><html lang='id'><head><meta charset='utf-8'>"
            f"<title>{args.business}</title></head><body>"
            f"<h1>{args.business}</h1>"
            f"<p>Paket {args.package} — {pkg['harga']}</p>"
            f"<ul>{items}</ul>"
            f"<p>Hubungi kami via WhatsApp.</p>"
            f"</body></html>",
            encoding="utf-8",
        )
        print("[build] template belum ada di repo — kerangka minimal dibuat")

    print(f"[build] {args.business} ({args.package}) -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
