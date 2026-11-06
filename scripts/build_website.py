#!/usr/bin/env python3
"""Build website agency on-demand (workflow_dispatch).

Menghasilkan website PESANAN KLIEN (paket W1/W2/W3) — bukan website agency
sendiri. Website agency di Cloudflare Pages adalah halaman marketing JasaBikin
(jual jasa), isinya harga/portofolio agency, jadi tidak bisa dipakai mentah
sebagai website klien. Script ini memakai template netral untuk bisnis klien.

Template: templates/site bila ada di repo, else template netral bawaan
(hero, layanan, kontak — dengan placeholder yang WAJIB diisi saat serah
terima, mis. nomor WA klien). Output: out/<business>-<package>/index.html
+ out/project-name.txt (slug Pages) + out/deploy-dir.txt (folder deploy).

Deploy ke Cloudflare Pages dilakukan workflow (wrangler), bukan script ini.

Jalankan: python3 scripts/build_website.py --business "Nama Usaha" --package W1
"""

from __future__ import annotations

import argparse
import re
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


def slugify(nama: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", nama.lower()).strip("-")
    return slug or "usaha"


def template_netral(business: str, package: str, harga: str, halaman: list[str]) -> str:
    items = "".join(f"<li>{h}</li>" for h in halaman)
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{business}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; color: #222; }}
header, section, footer {{ max-width: 720px; margin: 0 auto; padding: 24px; }}
.hero {{ background: #0f766e; color: #fff; }}
.hero h1 {{ margin: 0 0 8px; }}
.btn {{ display: inline-block; background: #25d366; color: #fff; padding: 12px 20px; border-radius: 8px; text-decoration: none; }}
.note {{ background: #fef9c3; padding: 12px; border-radius: 8px; }}
</style>
</head>
<body>
<header class="hero">
<h1>{business}</h1>
<p>Paket {package} — {harga}. Website profesional untuk usaha Anda.</p>
</header>
<section>
<h2>Layanan</h2>
<ul>{items}</ul>
</section>
<section>
<h2>Kontak</h2>
<p class="note">Serah terima: ganti tautan di bawah dengan nomor WA klien
yang sebenarnya sebelum situs diserahkan.</p>
<p><a class="btn" href="https://wa.me/NOMOR-WA-KLIEN">Chat WhatsApp</a></p>
<p>Jam buka: (diisi saat serah terima)</p>
</section>
<footer><p>&copy; {business}</p></footer>
</body>
</html>
"""


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
        (dest / "index.html").write_text(
            template_netral(args.business, args.package, pkg["harga"], pkg["halaman"]),
            encoding="utf-8",
        )
        print("[build] template netral bawaan dipakai")

    # Info untuk langkah deploy di workflow (bukan rahasia apa pun).
    (OUT / "project-name.txt").write_text(slugify(args.business), encoding="utf-8")
    (OUT / "deploy-dir.txt").write_text(str(dest.relative_to(ROOT)), encoding="utf-8")
    print(f"[build] {args.business} ({args.package}) -> {dest}")
    print(f"[build] project Pages: {slugify(args.business)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
