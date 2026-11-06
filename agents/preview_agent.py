"""
Fase 3 (bagian 2): Preview Agent.

Ambil screenshot full-page dari website yang baru di-build (pakai Playwright
headless), simpan sebagai file, dan siapkan staging_url yang dikirim ke
Telegram untuk direview manusia (lihat bot/telegram_bot.py).

CATATAN RESOURCE: Playwright + Chromium headless ini paling berat di antara
semua agent (butuh browser binary ~300MB+). Realistisnya ini dijalankan di
VPS, BUKAN di Termux/HP — kalau kamu split proses antar-device nanti,
preview_agent ini kandidat pertama yang tetap di server.

Screenshot diambil langsung dari file lokal (file://...), bukan lewat
STAGING_BASE_URL — supaya nggak bergantung nginx sudah nyala saat build
berlangsung. staging_url yang dikirim ke klien tetap pakai STAGING_BASE_URL,
dengan asumsi nginx/web server men-serve folder storage/staging/.
"""

from __future__ import annotations

import logging

from config.settings import STAGING_BASE_URL, STAGING_DIR
from core.database import get_project, save_project
from core.state import PipelineState
from models.schemas import ProjectStatus

logger = logging.getLogger("preview_agent")

VIEWPORT = {"width": 1280, "height": 900}


def capture_screenshot(project_id: str) -> str:
    from playwright.sync_api import sync_playwright  # import lokal, dependency berat

    site_dir = STAGING_DIR / project_id / "site"
    index_path = site_dir / "index.html"
    if not index_path.exists():
        raise FileNotFoundError(f"index.html belum ada di {site_dir}")

    screenshot_path = STAGING_DIR / project_id / "screenshot.png"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(f"file://{index_path.resolve()}")
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    return str(screenshot_path)


def run(state: PipelineState) -> PipelineState:
    project_id = state.get("project_id")
    if not project_id:
        state["error"] = "preview: project_id tidak ada di state"
        return state

    try:
        screenshot_path = capture_screenshot(project_id)
    except Exception as exc:  # noqa: BLE001
        state["error"] = f"preview: gagal screenshot - {exc}"
        return state

    staging_url = f"{STAGING_BASE_URL}/{project_id}/site/"

    project = get_project(project_id)
    if project is not None:
        project.staging_url = staging_url
        project.screenshot_path = screenshot_path
        project.status = ProjectStatus.STAGED
        save_project(project)

    state["staging_url"] = staging_url
    state["screenshot_path"] = screenshot_path
    state["status"] = "staged"
    return state
