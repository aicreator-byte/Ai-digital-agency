"""
Load semua konfigurasi dari .env + konstanta yang dipakai bareng-bareng
oleh seluruh agent. Jangan hardcode secret di file lain — selalu lewat sini.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Path dasar ---
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
STAGING_DIR = STORAGE_DIR / "staging"
DB_PATH = str(STORAGE_DIR / "agency.db")

# --- LLM provider ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")  # anthropic / openai / gemini
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- Telegram bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")

# --- Maps / scraping ---
# Backend: "google" (Places API New, butuh GOOGLE_MAPS_API_KEY + billing)
#       atau "osm" (OpenStreetMap/Overpass, gratis tanpa key/kartu)
SCRAPER_BACKEND = os.getenv("SCRAPER_BACKEND", "osm")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Payment (QRIS/DANA manual, bukan payment gateway) ---
# Path ke gambar barcode QRIS/DANA statis milik owner, dikirim otomatis
# oleh sistem ke klien. Konfirmasi dana masuk dilakukan MANUAL oleh owner
# lewat command bot Telegram (/sudah_bayar <project_id>), tidak ada
# polling otomatis ke payment gateway manapun.
DANA_QRIS_IMAGE_PATH = os.getenv("DANA_QRIS_IMAGE_PATH", "assets/qris_dana.jpeg")
DEFAULT_INVOICE_DUE_DAYS = int(os.getenv("DEFAULT_INVOICE_DUE_DAYS", "3"))

# --- WhatsApp (bridge lokal, nomor khusus jualan) ---
WA_ENABLED = os.getenv("WA_ENABLED", "false").lower() == "true"  # false = mode stub (cuma log)
WA_BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://127.0.0.1:3000")
WA_BRIDGE_TOKEN = os.getenv("WA_BRIDGE_TOKEN", "")
WA_WEBHOOK_PORT = int(os.getenv("WA_WEBHOOK_PORT", "8081"))
WA_DAILY_LIMIT = int(os.getenv("WA_DAILY_LIMIT", "15"))  # maks pesan dingin per hari
WA_COLD_DELAY = (45, 120)   # detik, jeda acak sebelum pesan dingin
WA_REPLY_DELAY = (3, 8)     # detik, jeda acak sebelum membalas

# --- Hosting (Cloudflare Pages; token dari vault custom.cloudflare) ---

# --- Aturan bisnis / pipeline ---
DEFAULT_MAX_REVISIONS = int(os.getenv("DEFAULT_MAX_REVISIONS", "5"))
STAGING_BASE_URL = os.getenv("STAGING_BASE_URL", "http://localhost:8080/staging")

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
STAGING_DIR.mkdir(parents=True, exist_ok=True)
