"""
Orchestrator: state machine yang nentuin agent mana jalan berikutnya
berdasarkan status project. Dibangun pakai LangGraph.

Di Batch 2 ini, node agent yang beneran (scraper, marketing, dst) belum ada.
Orchestrator otomatis pakai MOCK version (lihat agents/_mock.py) kalau modul
asli belum ditemukan, jadi kerangka pipeline bisa dites end-to-end dari sekarang.
Begitu Batch 3-6 selesai, node ini otomatis pakai agent asli tanpa perlu
ubah orchestrator.py.
"""

from __future__ import annotations

import importlib
import logging

from langgraph.graph import END, StateGraph

from core.state import PipelineState

logger = logging.getLogger("orchestrator")

# Mapping node -> (modul asli, nama fungsi run)
AGENT_MODULES = {
    "scrape": "agents.scraper_agent",
    "marketing": "agents.marketing_agent",
    "website": "agents.website_agent",
    "preview": "agents.preview_agent",
    "review": "agents.review_agent",
    "payment": "agents.payment_agent",
}


def _load_agent_run(node_name: str):
    """Coba import agent asli; kalau belum ada, fallback ke mock."""
    module_path = AGENT_MODULES[node_name]
    try:
        module = importlib.import_module(module_path)
        return module.run
    except ModuleNotFoundError:
        from agents._mock import get_mock_run

        logger.warning("Agent asli '%s' belum ada, pakai MOCK.", module_path)
        return get_mock_run(node_name)


def _make_node(node_name: str):
    def node(state: PipelineState) -> PipelineState:
        run_fn = _load_agent_run(node_name)
        try:
            return run_fn(state)
        except Exception as exc:  # noqa: BLE001 — agent gagal jangan crash seluruh pipeline
            logger.exception("Agent '%s' gagal", node_name)
            state["error"] = f"{node_name}: {exc}"
            return state

    return node


# ---------------------------------------------------------------------------
# Routing logic — berdasarkan status di state, bukan hardcode urutan linear
# ---------------------------------------------------------------------------

def _route_after_scrape(state: PipelineState) -> str:
    if state.get("error"):
        return END
    return "marketing"


def _route_after_marketing(state: PipelineState) -> str:
    if state.get("error"):
        return END
    if state.get("status") == "deal":
        return "website"
    return END  # belum deal, orchestrator berhenti; nanti dipicu lagi kalau lead follow-up jalan


def _route_after_website(state: PipelineState) -> str:
    if state.get("error"):
        return END
    return "preview"


def _route_after_preview(state: PipelineState) -> str:
    if state.get("error"):
        return END
    return "review"


def _route_after_review(state: PipelineState) -> str:
    """
    Setelah QA otomatis, project masuk status STAGED dan menunggu approve
    manual via Telegram (bot/telegram_bot.py). Orchestrator run BERHENTI
    di sini — lanjutannya (approve/revisi/reject) dipicu oleh callback bot,
    bukan otomatis lanjut, karena butuh keputusan manusia.
    """
    return END


def _route_after_payment(_state: PipelineState) -> str:
    return END


def build_graph():
    graph = StateGraph(PipelineState)

    for name in AGENT_MODULES:
        graph.add_node(name, _make_node(name))

    graph.set_entry_point("scrape")

    graph.add_conditional_edges("scrape", _route_after_scrape, {
        "marketing": "marketing", END: END,
    })
    graph.add_conditional_edges("marketing", _route_after_marketing, {
        "website": "website", END: END,
    })
    graph.add_conditional_edges("website", _route_after_website, {
        "preview": "preview", END: END,
    })
    graph.add_conditional_edges("preview", _route_after_preview, {
        "review": "review", END: END,
    })
    graph.add_conditional_edges("review", _route_after_review, {END: END})
    graph.add_conditional_edges("payment", _route_after_payment, {END: END})

    return graph.compile()


def resume_after_revision(state: PipelineState) -> PipelineState:
    """
    Dipanggil oleh bot Telegram waktu klien minta revisi.
    Balik langsung ke node website (skip scrape/marketing) dengan
    revision_notes yang sudah ditambahkan ke state.
    """
    website_node = _make_node("website")
    state = website_node(state)
    if state.get("error"):
        return state
    state = _make_node("preview")(state)
    if state.get("error"):
        return state
    return _make_node("review")(state)


def run_payment(state: PipelineState) -> PipelineState:
    """Dipanggil bot Telegram waktu klien approve."""
    return _make_node("payment")(state)
