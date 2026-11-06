"""
Fase 3 (bagian 3): Review Agent — QA otomatis.

Cakupan Batch 5 ini: SEO dasar, broken link internal, dan typo/grammar
(lewat LLM) pada teks yang di-generate. Speed & cross-device responsive
sebenarnya sudah tercakup separuh oleh desain template (viewport meta +
CSS grid auto-fit di style.css), jadi belum ada pengecekan otomatis
terpisah untuk itu di batch ini — bisa ditambah nanti kalau perlu
(misal integrasi Lighthouse CI).

KEPUTUSAN DESAIN: review ini bersifat ADVISORY, bukan blocking — kalau
ketemu masalah, dicatat sebagai warning (log + disimpan ke state), tapi
pipeline tetap lanjut ke tahap approve Telegram. Alasannya: auto-fix loop
otomatis (tanpa manusia) berisiko infinite-loop kalau LLM salah persepsi
soal "masalah"-nya, dan versi manual-review (kamu lihat sendiri di
screenshot/staging) sudah jadi pengaman utama sebelum publish. Kalau nanti
mau diperketat jadi blocking, tinggal ubah logic di run().
"""

from __future__ import annotations

import json
import logging
import re

from config.settings import STAGING_DIR
from core.llm import generate
from core.state import PipelineState

logger = logging.getLogger("review_agent")

_TYPO_SYSTEM_PROMPT = """\
Kamu proofreader teks Bahasa Indonesia. Baca teks berikut, cari typo atau
kesalahan tata bahasa yang jelas saja (bukan gaya penulisan). Jawab HANYA
dengan JSON array of string berisi daftar masalah yang ditemukan (kosongkan
array kalau tidak ada masalah). Contoh: ["kata 'layanan' salah ketik jadi
'layannan' di bagian FAQ"]"""


def check_seo_basics(html: str) -> list[str]:
    issues = []
    title_match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    if not title_match or not title_match.group(1).strip():
        issues.append("Tag <title> kosong")

    desc_match = re.search(r'name="description" content="(.*?)"', html)
    if not desc_match:
        issues.append("Meta description tidak ditemukan")
    elif len(desc_match.group(1)) > 160:
        issues.append("Meta description terlalu panjang (>160 karakter)")

    if 'name="viewport"' not in html:
        issues.append("Meta viewport tidak ada (bahaya untuk mobile-friendliness)")

    return issues


def check_broken_links(html: str, site_dir) -> list[str]:
    issues = []
    for href in re.findall(r'href="([^"]+)"', html):
        if href.startswith("http") or href.startswith("#"):
            continue  # link eksternal (wa.me dst) atau anchor, skip
        local_path = site_dir / href
        if not local_path.exists():
            issues.append(f"Link lokal rusak: {href}")

    for src in re.findall(r'src="([^"]+)"', html):
        if src.startswith("http"):
            continue
        local_path = site_dir / src
        if not local_path.exists():
            issues.append(f"Asset rusak (file tidak ditemukan): {src}")

    return issues


def check_typos(html: str) -> list[str]:
    text_only = re.sub(r"<[^>]+>", " ", html)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    raw = generate(text_only, system=_TYPO_SYSTEM_PROMPT, max_tokens=500)
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        logger.warning("Review typo-check: LLM tidak balas JSON valid, dilewati.")
        return []


def run(state: PipelineState) -> PipelineState:
    project_id = state.get("project_id")
    if not project_id:
        state["error"] = "review: project_id tidak ada di state"
        return state

    site_dir = STAGING_DIR / project_id / "site"
    html_files = sorted(site_dir.glob("*.html"))
    if not html_files:
        state["error"] = f"review: belum ada file HTML di {site_dir}"
        return state

    issues = []
    for html_path in html_files:
        html = html_path.read_text(encoding="utf-8")
        page_issues = check_seo_basics(html) + check_broken_links(html, site_dir)
        try:
            page_issues += check_typos(html)
        except Exception:  # noqa: BLE001 — typo-check gagal jangan sampai blokir pipeline
            logger.exception("Typo-check gagal untuk %s, dilewati.", html_path.name)
        issues += [f"[{html_path.name}] {i}" for i in page_issues]

    if issues:
        logger.warning("Review menemukan %d catatan untuk project %s: %s", len(issues), project_id, issues)

    state["review_issues"] = issues  # informasional, bukan penghalang
    state["status"] = "review"
    return state
