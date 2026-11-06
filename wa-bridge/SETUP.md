# Setup WA Bridge — yang harus dilakukan Di

## Keputusan Di (2026-10-15): pakai nomor publik agency 0881-1722-942
Di memutuskan bridge memakai nomor publik yang sama (bukan nomor cadangan).
Risiko kebanned ditanggung — kalau nomor ini kebanned, jalur kontak website
ikut mati. Dokumen ini disesuaikan dengan keputusan tersebut.

## Yang Di siapkan

1. **Nomor 0881-1722-942 aktif** — WhatsApp terinstal & terverifikasi.
   Lengkapi foto + nama profil bila belum.
2. Beri tahu operator (chat) kalau nomor sudah siap → operator menjalankan
   bridge, QR muncul di terminal.
3. **Scan QR** dari WhatsApp nomor tersebut: Pengaturan → Perangkat Tertaut →
   Tautkan Perangkat. Sesi tersimpan di `../whatsapp/auth/` (sekali saja;
   scan ulang hanya kalau sesi logout/kedaluwarsa).
4. Verifikasi: operator jalankan `check.sh` → harus `ready: true`.
5. **Ikuti `WARMUP.md` sampai Fase 3.** Jangan minta diaktifkan sebelum itu.
6. Setelah pemanasan selesai + Di setuju eksplisit → operator set
   `WA_ENABLED=true` di `.env`. Sebelum itu semua kiriman cuma di-log.

## Variabel `.env` (operator yang isi, Di tidak perlu)

- `WA_BRIDGE_TOKEN` — string acak, jadi password HTTP bridge. Wajib diisi
  sebelum bridge dipakai (jangan kosong saat `WA_ENABLED=true`).
- `WA_ENABLED` — `false` (default, dry-run) / `true` (kirim beneran).
- `WA_DAILY_LIMIT` — default 15 (maks pesan dingin/hari). Jangan naikkan
  tanpa izin Di.
- `WA_BRIDGE_URL` — default `http://127.0.0.1:3000` (jangan ubah).

## Troubleshooting

- **QR tidak muncul**: pastikan `node bridge.js` jalan di folder
  `../whatsapp/` (butuh `npm install` sekali).
- **Scan sukses tapi langsung 401/logout**: hapus `../whatsapp/auth/`,
  jalankan ulang, scan lagi. Kalau berulang, jeda beberapa jam lalu coba
  dari jaringan berbeda (indikasi reputasi IP/proxy).
- **Sesi mati tiba-tiba**: bridge reconnect otomatis (3 detik). Kalau status
  `loggedOut` → hapus `auth/`, scan ulang.
- **Nomor ke-ban**: lihat `WARMUP.md` (ganti SIM, `auth/` baru, ulang
  pemanasan). Jangan pernah pair nomor utama sebagai "pengganti cepat".

## Titik integrasi ke pipeline (CATATAN — jangan ubah kode tanpa izin Di)

Alur kirim sudah terkabel di kode, tinggal diaktifkan:

1. `agents/marketing_agent.py` → `send_outreach(bisnis, isi, cold=True)`
   memanggil `core.whatsapp.send_text()`.
2. `core/whatsapp.py` → validasi nomor, cek counter harian
   (`storage/wa_daily.json`, batas `WA_DAILY_LIMIT`), jeda acak
   (`WA_COLD_DELAY` 45–120 dtk), lalu `POST 127.0.0.1:3000/send`.
   `WA_ENABLED=false` = dry-run (log saja).
3. `bot/wa_webhook.py` → pesan masuk dari prospek diteruskan bridge ke
   `http://127.0.0.1:8081/wa/incoming`, diklasifikasi
   (`classify_reply`), balasan FAQ dikirim dengan `cold=False`
   (tidak memakan jatah harian).
4. Orchestrator: node `marketing` (`core/orchestrator.py`,
   `_load_agent_run("marketing")` → `agents.marketing_agent`) — tahap
   yang memicu `send_outreach`. Aturan keras skill: draft WAJIB approval
   Di sebelum kirim.

Yang BELUM ada: supervisor agar `bridge.js` hidup persisten
(mati tiap VM diganti ±2 jam — perlu masuk watchdog/`infra/watch.sh`;
jangan tambah sebelum Di setuju).
