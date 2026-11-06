"""
Mock agent — dipakai orchestrator sebagai fallback kalau agent asli
(agents/scraper_agent.py, dst) belum ada. Tujuannya cuma supaya alur
status/routing di orchestrator bisa dites dari Batch 2, sebelum logic
asli tiap agent dibangun di Batch 3-6.

JANGAN dipakai di production — orchestrator otomatis berhenti pakai ini
begitu modul asli (misal agents/scraper_agent.py) sudah dibuat.
"""

from __future__ import annotations

from typing import Callable

from core.state import PipelineState


def _mock_scrape(state: PipelineState) -> PipelineState:
    state["status"] = "scored"
    return state


def _mock_marketing(state: PipelineState) -> PipelineState:
    # Simulasi: anggap prospek langsung deal supaya pipeline bisa dites lanjut
    state["status"] = "deal"
    return state


def _mock_website(state: PipelineState) -> PipelineState:
    state["status"] = "in_production"
    state["brief"] = state.get("brief") or {"nama": "Contoh Usaha"}
    return state


def _mock_preview(state: PipelineState) -> PipelineState:
    state["staging_url"] = "http://localhost:8080/staging/mock-project"
    state["screenshot_path"] = "storage/staging/mock-project/screenshot.png"
    state["status"] = "staged"
    return state


def _mock_review(state: PipelineState) -> PipelineState:
    state["status"] = "review"
    return state


def _mock_payment(state: PipelineState) -> PipelineState:
    state["status"] = "paid"
    return state


_MOCKS: dict[str, Callable[[PipelineState], PipelineState]] = {
    "scrape": _mock_scrape,
    "marketing": _mock_marketing,
    "website": _mock_website,
    "preview": _mock_preview,
    "review": _mock_review,
    "payment": _mock_payment,
}


def get_mock_run(node_name: str) -> Callable[[PipelineState], PipelineState]:
    return _MOCKS[node_name]
