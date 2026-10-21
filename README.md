# Workflow Agency — JasaBikin (AI Digital Agency)

Tiga pekerjaan otomatis (GitHub Actions). Dijalankan dari repo ini, tanpa
server always-on.

## Jadwal

| Job | Jadwal | Yang dilakukan |
|---|---|---|
| `prospek-pagi` | Tiap hari 00:00 UTC = **07:00 WIB** | Cari prospek baru via OSM/Overpass (tanpa API key) untuk tiap target di `prospect_targets.yaml`, simpan hasilnya sebagai artifact `leads-YYYY-MM-DD.json`. |
| `followup-sore` | Tiap hari 10:00 UTC = **17:00 WIB** | Buat **DRAF** pesan follow-up untuk prospek tanpa website (kandidat paket website) sebagai artifact. TIDAK mengirim apa pun. |
| `bangun-website` | Manual (`workflow_dispatch`) | Build website dari template untuk satu bisnis (input: nama bisnis + paket W1/W2/W3). Hasilnya artifact ZIP. Deploy ke Cloudflare Pages hanya jalan bila secret `CLOUDFLARE_API_TOKEN` diset. |

## Yang TIDAK dilakukan workflow ini (sengaja)

- **Tidak mengirim WhatsApp.** Pengiriman WA butuh bridge (saat ini mati) dan
  persetujuan Di per pesan. Workflow hanya menyiapkan draf.
- **Tidak memakai Google Places API.** Butuh billing Google Cloud (Di tidak
  punya kartu). Scraper memakai backend OSM/Overpass (`SCRAPER_BACKEND=osm`,
  default) — gratis, tanpa key.
- **Tidak memakai LLM.** Tidak ada secret AI yang dibutuhkan untuk job
  terjadwal. Build website memakai template Jinja (copy AI menyusul bila
  secret LLM diset — saat ini tidak).
- **Tidak menyimpan database prospek di repo.** DB (`storage/agency.db`)
  berisi data bisnis dan TIDAK ikut di-push (lihat `.gitignore`). Setiap run
  Actions mulai dari DB kosong; hasil scrape keluar sebagai artifact, bukan
  commit ke repo.

## Secret yang dibutuhkan

- Tidak ada (untuk kedua job terjadwal).
- Opsional: `CLOUDFLARE_API_TOKEN` — hanya untuk deploy Pages pada job
  `bangun-website`. Tanpa secret ini, job tetap menghasilkan ZIP artifact.

## Target prospek default

Diambil dari data agency yang sudah ada (hanya kategori + lokasi, tanpa nama
bisnis): klinik di Bandung (108 bisnis, 81 lead scored). Ubah
`prospect_targets.yaml` untuk menambah kategori/lokasi.
