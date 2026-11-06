# WhatsApp (nomor khusus jualan)

Pakai SIM/nomor BARU, bukan nomor pribadi. Cara ini tidak resmi, jadi ada risiko nomor diblokir.

## Setup sekali
1. Butuh Node 18+. Di folder `whatsapp/`: `npm install`
2. Di `.env` isi `WA_BRIDGE_TOKEN` dengan string acak (bebas), biarkan `WA_ENABLED=false` dulu.
3. Jalankan `node bridge.js`, scan QR yang muncul lewat WhatsApp nomor jualan
   (Pengaturan > Perangkat Tertaut). Sesi tersimpan di folder `auth/`.
4. Terminal lain, dari folder utama: `python -m bot.wa_webhook`
5. Tes dengan nomor teman: isi `nomor_wa` bisnis tes dengan nomor teman, set `WA_ENABLED=true`.

## Aturan aman
- Minggu pertama: maksimal 10-15 pesan dingin per hari (`WA_DAILY_LIMIT`).
- Jangan kirim ke nomor yang sama berulang kali; follow-up maksimal 2x.
- Kalau nomor kena banned: ganti SIM, hapus folder `auth/`, scan ulang.

## Di VPS
Jalankan `bridge.js`, `bot.wa_webhook`, dan `bot.telegram_bot` sebagai tiga service
(systemd atau pm2) dengan auto-restart supaya hidup lagi kalau server restart.
