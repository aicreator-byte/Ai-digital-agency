"""
Loader paket website dari config/packages.yaml. Dipisah dari settings.py
supaya gampang di-reload/dites sendiri tanpa nyentuh env vars.
"""

from __future__ import annotations

from functools import lru_cache

import yaml

from config.settings import BASE_DIR

PACKAGES_PATH = BASE_DIR / "config" / "packages.yaml"

DEFAULT_PACKAGE = "w1"

NAV_LABELS = {
    "index": "Beranda",
    "layanan": "Layanan",
    "tentang": "Tentang Kami",
    "galeri": "Galeri",
    "blog": "Blog",
    "kontak": "Kontak",
}


@lru_cache
def _load_all() -> dict:
    with open(PACKAGES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_package(paket_id: str | None) -> dict:
    packages = _load_all()
    paket_id = paket_id or DEFAULT_PACKAGE
    if paket_id not in packages:
        raise ValueError(
            f"Paket '{paket_id}' tidak dikenal. Pilihan: {list(packages.keys())}"
        )
    spec = dict(packages[paket_id])
    spec["id"] = paket_id
    return spec


def nav_items(package_spec: dict, current_page: str) -> list[dict]:
    items = []
    for page in package_spec["pages"]:
        href = "index.html" if page == "index" else f"{page}.html"
        items.append({
            "label": NAV_LABELS.get(page, page.title()),
            "href": href,
            "active": page == current_page,
        })
    return items
