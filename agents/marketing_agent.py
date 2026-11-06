"""
Fase 2: Outreach.

CATATAN ARSITEKTUR (sama seperti scraper_agent): outreach itu inherently
ASYNC — setelah pesan pertama dikirim, sistem harus NUNGGU balasan calon
klien (bisa jam/hari kemudian) sebelum tahu apakah lanjut ke DEAL atau
tidak. Makanya:

- `run(state)` cuma kirim pesan pertama, set status jadi CONTACTED, lalu
  berhenti (orchestrator sudah didesain berhenti di sini kalau status
  belum "deal" — lihat _route_after_marketing di core/orchestrator.py).
- `process_reply()` adalah entry point terpisah yang dipanggil ketika
  balasan masuk (nanti disambungkan ke webhook WhatsApp/email — BELUM
  dibangun di batch ini, karena butuh keputusan channel/provider dulu).
- `check_follow_ups()` adalah batch job (mirip find_leads) buat nge-scan
  lead yang belum dibalas setelah N hari dan kirim follow-up otomatis.

Pengiriman lewat core/whatsapp.py (bridge Baileys, nomor khusus jualan).
Kalau WA_ENABLED=false, pesan cuma di-log (mode stub). Balasan klien masuk
lewat bot/wa_webhook.py yang memanggil process_reply().
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from core.database import get_business, get_lead, get_leads_by_status, save_lead, save_message
from core.llm import generate
from core.whatsapp import send_text
from core.state import PipelineState
from models.schemas import Business, LeadStatus, Message

logger = logging.getLogger("marketing_agent")

FOLLOW_UP_AFTER_DAYS = 3
MAX_FOLLOW_UPS = 2

_DRAFT_SYSTEM_PROMPT = """\
Kamu adalah AI marketing untuk agensi digital yang menawarkan jasa pembuatan
website profesional ke pemilik bisnis lokal. Tulis pesan WhatsApp singkat,
ramah, bahasa Indonesia santai-sopan (bukan formal kaku), personal (sebut
nama usaha & hal spesifik tentang bisnisnya), dan JANGAN terkesan spam/template.
Selalu diakhiri ajakan lembut untuk ngobrol lebih lanjut, bukan hard-sell.
Maksimal 4-5 kalimat."""

_CLASSIFY_SYSTEM_PROMPT = """\
Kamu mengklasifikasikan balasan calon klien terhadap tawaran jasa pembuatan
website. Jawab HANYA dengan salah satu kata ini (tanpa penjelasan lain):
DEAL (klien setuju/minta lanjut), INTERESTED (tertarik tapi belum deal,
masih nanya-nanya), NOT_INTERESTED (menolak/tidak berminat)."""


def draft_initial_message(business: Business) -> str:
    context = (
        f"Nama usaha: {business.nama}\n"
        f"Kategori: {business.kategori}\n"
        f"Lokasi: {business.lokasi}\n"
        f"Punya website: {'ya' if business.has_website else 'tidak'}\n"
    )
    if business.has_website and business.website_score is not None:
        context += f"Skor kualitas website saat ini: {business.website_score}/100\n"

    prompt = f"{context}\nTulis pesan outreach pertama untuk usaha ini."
    return generate(prompt, system=_DRAFT_SYSTEM_PROMPT)


def classify_reply(reply_text: str) -> LeadStatus:
    result = generate(reply_text, system=_CLASSIFY_SYSTEM_PROMPT, max_tokens=10).strip().upper()
    mapping = {
        "DEAL": LeadStatus.DEAL,
        "INTERESTED": LeadStatus.INTERESTED,
        "NOT_INTERESTED": LeadStatus.NOT_INTERESTED,
    }
    return mapping.get(result, LeadStatus.INTERESTED)  # default aman: anggap masih perlu follow-up


def draft_faq_reply(business: Business, client_message: str) -> str:
    context = f"Nama usaha calon klien: {business.nama} ({business.kategori})"
    prompt = f"{context}\n\nPesan dari calon klien: \"{client_message}\"\n\nBalas pesan ini."
    return generate(prompt, system=_DRAFT_SYSTEM_PROMPT)


def send_outreach(business: Business, isi: str, agent: str = "marketing_agent", cold: bool = True) -> bool:
    """Kirim lewat WhatsApp (atau stub kalau WA_ENABLED=false). cold=True untuk pesan
    ke orang yang belum pernah chat (kena batas harian); cold=False untuk membalas."""
    ok = send_text(business.nomor_wa, isi, cold=cold)
    if ok:
        save_message(Message(business_id=business.id, isi=isi, agent=agent, arah="out"))
    return ok


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def process_reply(lead_id: str, business_id: str, reply_text: str) -> LeadStatus:
    """Dipanggil waktu balasan dari klien masuk (lewat integrasi channel nanti)."""
    business = get_business(business_id)
    if business is None:
        raise ValueError(f"Business {business_id} tidak ditemukan")

    save_message(Message(business_id=business_id, isi=reply_text, agent="client", arah="in"))

    status = classify_reply(reply_text)

    if status == LeadStatus.INTERESTED:
        # Masih nanya-nanya -> balas FAQ, tetap INTERESTED sampai eksplisit deal
        faq_reply = draft_faq_reply(business, reply_text)
        send_outreach(business, faq_reply, cold=False)

    return status


def check_follow_ups() -> int:
    """Batch job: scan lead CONTACTED yang belum dibalas > FOLLOW_UP_AFTER_DAYS, kirim follow-up."""
    leads = get_leads_by_status(LeadStatus.CONTACTED)
    now = datetime.utcnow()
    sent = 0

    for lead in leads:
        if lead.last_contacted_at is None:
            continue
        if now - lead.last_contacted_at < timedelta(days=FOLLOW_UP_AFTER_DAYS):
            continue

        business = get_business(lead.business_id)
        if business is None:
            continue

        follow_up_msg = generate(
            f"Ini follow-up ke calon klien {business.nama} yang belum membalas pesan pertama kita "
            f"sekitar {FOLLOW_UP_AFTER_DAYS} hari lalu. Tulis pesan follow-up singkat, tidak maksa.",
            system=_DRAFT_SYSTEM_PROMPT,
        )
        if not send_outreach(business, follow_up_msg):
            break  # kemungkinan batas harian tercapai, lanjut besok
        lead.last_contacted_at = now
        save_lead(lead)
        sent += 1

    return sent


def run(state: PipelineState) -> PipelineState:
    """Node orchestrator: kirim pesan outreach PERTAMA, lalu berhenti (nunggu balasan)."""
    business_id = state.get("business_id")
    if not business_id:
        state["error"] = "marketing: business_id tidak ada di state"
        return state

    business = get_business(business_id)
    if business is None:
        state["error"] = f"marketing: business {business_id} tidak ditemukan"
        return state

    message = draft_initial_message(business)
    if not send_outreach(business, message):
        state["error"] = "marketing: pesan tidak terkirim (nomor tidak valid, batas harian, atau bridge WA mati)"
        return state

    lead_id = state.get("lead_id")
    if lead_id:
        lead = get_lead(lead_id)
        if lead is not None:
            lead.status = LeadStatus.CONTACTED
            lead.last_contacted_at = datetime.utcnow()
            save_lead(lead)

    state["status"] = "contacted"
    return state
