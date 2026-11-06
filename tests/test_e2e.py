"""
Batch 7: Test integrasi end-to-end.

Ini menjalankan RANTAI AGENT ASLI (website_agent, preview_agent,
review_agent, payment_agent — bukan agents/_mock.py) untuk satu bisnis
dummy, dari titik "sudah DEAL" (skip scrape+marketing karena keduanya
butuh Google Places API & LLM beneran yang lebih pas dites terpisah
lewat data asli, bukan dummy) sampai ke publish.

LLM (core.llm.generate), pemanggilan Midtrans, dan deploy Netlify di-MOCK
(lihat blok `unittest.mock.patch` di bawah) supaya:
1. Bisa jalan tanpa API key asli / tanpa biaya asli
2. Tetap menguji SEMUA logic asli di tiap agent (state transition,
   penulisan file, penyimpanan database, penentuan paket, dst) — cuma
   panggilan ke layanan eksternal yang diganti.

Cara jalanin (di VPS/Termux, setelah `pip install -r requirements.txt`):
    python3 -m tests.test_e2e

CATATAN JUJUR: script ini ditulis & di-review manual dengan hati-hati,
TAPI belum pernah benar-benar dieksekusi, karena sandbox pembuatannya
tidak punya pydantic/langgraph terinstall (tidak ada akses internet).
Jalankan ini pertama kali begitu kamu setup di VPS/Termux, sebelum pakai
sistemnya untuk klien beneran — kalau ada AssertionError atau exception,
itu sinyal ada yang perlu diperbaiki sebelum dipakai produksi.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from core.database import get_project, init_db, save_business, save_lead, save_project
from core.state import initial_state
from models.schemas import Business, Lead, LeadStatus

FAKE_SITE_CONTENT = {
    "headline": "Klinik Sehat Sentosa — Kesehatan Keluarga Terpercaya",
    "subheadline": "Melayani Bandung Timur sejak 2015",
    "about": "Klinik Sehat Sentosa menyediakan layanan kesehatan keluarga lengkap.",
    "meta_description": "Klinik keluarga terpercaya di Bandung Timur",
    "services": [{"name": "Konsultasi Umum", "desc": "Dokter berpengalaman"}],
    "faq": [{"q": "Jam buka?", "a": "08.00 - 20.00 setiap hari"}],
    "blog_posts": [{"title": "5 Tips Sehat", "excerpt": "Cara jaga imun tubuh."}],
    "cta_text": "Buat Janji via WhatsApp",
}


def fake_llm_generate(prompt: str, system: str = "", max_tokens: int = 500) -> str:
    """Pengganti generate() asli — dipasang di agents.website_agent & agents.review_agent
    (bukan core.llm langsung, karena keduanya import 'from core.llm import generate' —
    patch harus di titik pemakaian, bukan titik definisi). Deteksi jenis panggilan dari
    system prompt."""
    if "copywriting" in system.lower():
        return json.dumps(FAKE_SITE_CONTENT)
    if "proofreader" in system.lower():
        return "[]"  # anggap tidak ada typo
    if "klasifikasikan balasan" in system.lower():
        return "DEAL"
    return "OK"


def run_e2e_test() -> None:
    print("=== Setup: init DB + business/lead dummy (anggap hasil scrape+marketing) ===")
    init_db()

    business = Business(
        nama="Klinik Sehat Sentosa",
        kategori="klinik",  # sengaja pilih kategori yang ada di package_rules.yaml -> w3
        lokasi="Bandung Timur",
        alamat="Jl. Sehat No. 10",
        nomor_wa="081234567890",
        has_website=False,
    )
    save_business(business)

    lead = Lead(business_id=business.id, score=95, status=LeadStatus.DEAL)
    save_lead(lead)
    print(f"Business dibuat: {business.id} ({business.nama})")

    state = initial_state(business.id, lead.id, project_id="", brief={
        "nama": business.nama,
        "alamat": business.alamat,
        "nomor_wa": business.nomor_wa,
        "harga_override": 1_500_000,  # override manual karena harga_estimasi di packages.yaml masih null
    })
    state.pop("project_id")  # biar website_agent yang bikinin project baru

    with patch("agents.website_agent.generate", side_effect=fake_llm_generate), \
         patch("agents.review_agent.generate", side_effect=fake_llm_generate):
        print("\n=== Fase 3a: website_agent.run() ===")
        from agents import website_agent
        state = website_agent.run(state)
        assert not state.get("error"), f"website_agent gagal: {state.get('error')}"
        assert state["project_id"], "project_id tidak ter-set"
        print(f"OK - project_id={state['project_id']}, status={state['status']}")

        print("\n=== Fase 3b: preview_agent.run() (Playwright ASLI, bukan mock) ===")
        from agents import preview_agent
        state = preview_agent.run(state)
        assert not state.get("error"), f"preview_agent gagal: {state.get('error')}"
        assert state["status"] == "staged"
        print(f"OK - screenshot={state['screenshot_path']}, staging_url={state['staging_url']}")

        print("\n=== Fase 3c: review_agent.run() (QA ASLI) ===")
        from agents import review_agent
        state = review_agent.run(state)
        assert not state.get("error"), f"review_agent gagal: {state.get('error')}"
        issues = state.get("review_issues", [])
        print(f"OK - status={state['status']}, review_issues={issues}")

    print("\n=== Simulasi approve manual via Telegram (tanpa bot beneran) ===")
    project = get_project(state["project_id"])
    project.brief["harga_override"] = 1_500_000
    save_project(project)

    print("\n=== Fase 4a: payment_agent.run() (invoice QRIS manual, WA di-mock) ===")
    from agents import payment_agent

    with patch.object(payment_agent, "_notify_image", return_value=True):
        state["project_id"] = project.id
        state = payment_agent.run(state)
        assert not state.get("error"), f"payment_agent gagal: {state.get('error')}"
        assert state["status"] == "invoiced"
        print(f"OK - status={state['status']}")

    print("\n=== Fase 4b: confirm_payment() manual owner (deploy di-mock) ===")
    with patch.object(payment_agent, "deploy_to_cf_pages", return_value=("fake-project", "https://fake-agency-site.pages.dev")), \
         patch.object(payment_agent, "_notify", return_value=True):
        result = payment_agent.confirm_payment(project.id)
        assert result["status"] == "published", f"status akhir: {result['status']}"
        print(f"OK - project {project.id} berhasil di-deploy (simulasi)")

    final_project = get_project(project.id)
    print(f"\n=== HASIL AKHIR ===\nstatus: {final_project.status}\nlive_url: {final_project.live_url}\npaket: {final_project.brief.get('paket')}")
    assert final_project.status == "published"
    assert final_project.brief.get("paket") == "w3", "kategori 'klinik' harusnya auto-assign ke paket w3"

    print("\n✅ SEMUA TAHAP LOLOS — pipeline end-to-end nyambung dengan benar.")


if __name__ == "__main__":
    run_e2e_test()
