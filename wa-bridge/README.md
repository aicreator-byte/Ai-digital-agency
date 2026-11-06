# WA Bridge — nomor cadangan (tidak resmi)

Fondasi koneksi WhatsApp tidak resmi untuk outreach agency.
Keputusan Di (2026-10-14): pakai **nomor cadangan**, nomor utama tidak dipertaruhkan.

## Isi folder ini

- `SETUP.md` — langkah untuk Di (aktivasi nomor, scan QR) + titik integrasi pipeline.
- `WARMUP.md` — rencana pemanasan nomor cadangan sebelum outreach.
- `check.sh` — cek status bridge (perlu bridge jalan).

## Kode kanonis (sudah ada, jangan diduplikasi)

| Komponen | Lokasi | Fungsi |
|---|---|---|
| Bridge Baileys | `../whatsapp/bridge.js` | QR pairing, sesi di `../whatsapp/auth/`, HTTP API `127.0.0.1:3000` (`/status`, `/send`, `/send-image`) |
| Klien Python | `../core/whatsapp.py` | Rate limit, dry-run default, counter harian |
| Webhook masuk | `../bot/wa_webhook.py` | Terima balasan prospek |
| Agen marketing | `../agents/marketing_agent.py` | `send_outreach()` → `send_text(..., cold=True)` |
| Konfigurasi | `../config/settings.py` + `.env` | `WA_ENABLED`, `WA_BRIDGE_TOKEN`, `WA_DAILY_LIMIT`, `WA_COLD_DELAY`, `WA_REPLY_DELAY` |

Teknologi: `@whiskeysockets/baileys` 6.7.x (stabil; v7 masih RC dengan
breaking changes — jangan upgrade tanpa kebutuhan). Sesi: multi-file auth,
re-pairing via QR bila logout/kedaluwarsa.

## Status default: MATI

`WA_ENABLED=false` → semua kiriman cuma di-log (dry-run). Tidak ada pesan
yang bisa terkirim tanpa Di membalik ke `true` secara eksplisit.
