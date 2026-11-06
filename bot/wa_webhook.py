"""
Penerima pesan WhatsApp masuk (dari whatsapp/bridge.js).

Alur per pesan masuk:
1. Cari bisnis berdasarkan nomor pengirim; kalau tidak dikenal, abaikan.
2. Lead belum DEAL  -> process_reply() (klasifikasi + balas FAQ otomatis),
   simpan status baru; kalau DEAL, kabari owner lewat Telegram.
3. Lead sudah DEAL  -> jangan dibalas bot, teruskan ke owner di Telegram
   (mis. klien bilang "sudah transfer") supaya kamu yang cek dan konfirmasi.

Jalankan: python -m bot.wa_webhook
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from agents.marketing_agent import process_reply
from config.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_OWNER_CHAT_ID,
    WA_BRIDGE_TOKEN,
    WA_WEBHOOK_PORT,
)
from core.database import get_conn, init_db, save_lead, save_message
from core.whatsapp import normalize_number
from models.schemas import Business, Lead, LeadStatus, Message

logger = logging.getLogger("wa_webhook")


def notify_owner(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_CHAT_ID):
        logger.info("[OWNER] %s", text)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_OWNER_CHAT_ID, "text": text},
            timeout=15,
        )
    except requests.RequestException:
        logger.exception("Gagal kirim notifikasi Telegram ke owner")


def find_business_by_number(number: str) -> Business | None:
    with get_conn() as conn:
        rows = conn.execute("SELECT data FROM businesses").fetchall()
    for row in rows:
        b = Business.model_validate_json(row["data"])
        if normalize_number(b.nomor_wa) == number:
            return b
    return None


def find_lead(business_id: str) -> Lead | None:
    with get_conn() as conn:
        rows = conn.execute("SELECT data FROM leads WHERE business_id = ?", (business_id,)).fetchall()
    leads = [Lead.model_validate_json(r["data"]) for r in rows]
    return max(leads, key=lambda l: l.created_at) if leads else None


def handle_incoming(number_raw: str, text: str) -> None:
    number = normalize_number(number_raw)
    if number is None:
        return
    business = find_business_by_number(number)
    if business is None:
        logger.info("Pesan dari nomor tak dikenal %s, diabaikan.", number)
        return
    lead = find_lead(business.id)
    if lead is None:
        return

    if lead.status == LeadStatus.DEAL:
        save_message(Message(business_id=business.id, isi=text, agent="client", arah="in"))
        notify_owner(f"💬 {business.nama} (sudah DEAL) bilang:\n{text}")
        return

    status = process_reply(lead.id, business.id, text)
    lead.status = status
    save_lead(lead)
    logger.info("%s -> %s", business.nama, status.value)

    if status == LeadStatus.DEAL:
        notify_owner(f"🎉 DEAL dengan {business.nama}!\nPesan klien: {text}")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        if self.path != "/wa/incoming" or self.headers.get("x-token", "") != WA_BRIDGE_TOKEN:
            self.send_response(403)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
            number, text = str(data["number"]), str(data["text"])
        except (ValueError, KeyError):
            self.send_response(400)
            self.end_headers()
            return

        # jawab bridge cepat, proses (LLM + jeda kirim) di thread terpisah
        self.send_response(200)
        self.end_headers()
        threading.Thread(target=_safe_handle, args=(number, text), daemon=True).start()

    def log_message(self, *args):  # sepikan log HTTP bawaan
        pass


def _safe_handle(number: str, text: str) -> None:
    try:
        handle_incoming(number, text)
    except Exception:  # noqa: BLE001 — satu pesan gagal jangan matikan server
        logger.exception("Gagal proses pesan masuk dari %s", number)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    logger.info("Webhook WA jalan di 127.0.0.1:%s", WA_WEBHOOK_PORT)
    ThreadingHTTPServer(("127.0.0.1", WA_WEBHOOK_PORT), _Handler).serve_forever()
