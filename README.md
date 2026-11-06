# Workflow Agency — JasaBikin (AI Digital Agency)

Tiga pekerjaan otomatis (GitHub Actions). Dijalankan dari repo ini, tanpa
server always-on.

## Jadwal

| Job | Jadwal | Yang dilakukan |
|---|---|---|
| `prospek-pagi` | Tiap hari 00:00 UTC = **07:00 WIB** | Cari prospek baru via OSM/Overpass (tanpa API key) untuk tiap target di `prospect_targets.yaml`, simpan hasilnya sebagai artifact `leads-YYYY-MM-DD.json`, + buka Issue ringkasan (jumlah lead + link artifact saja — isi data bisnis tetap di artifact, tidak masuk Issue/repo). Issue lama yang sejenis ditutup otomatis. |
| `followup-sore` | Tiap hari 10:00 UTC = **17:00 WIB** | Buat **DRAF** pesan follow-up untuk prospek tanpa website (kandidat paket website) sebagai artifact + buka Issue antrean berisi draf siap kirim (nama + pesan saja, tanpa nomor telepon). Issue lama yang sejenis ditutup otomatis. TIDAK mengirim apa pun. |
| `bangun-website` | Manual (`workflow_dispatch`) | Build website PESANAN KLIEN dari template netral untuk satu bisnis (input: nama bisnis + paket W1/W2/W3). Hasilnya artifact ZIP + (bila 2 secret Pages diset) deploy beneran ke Cloudflare Pages via wrangler, URL live `https://<slug-bisnis>.pages.dev`. |

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
- Untuk deploy Pages pada job `bangun-website` (opsional, tanpa ini job
  tetap menghasilkan ZIP artifact):
  - `CLOUDFLARE_API_TOKEN` — dari Cloudflare Dashboard → My Profile →
    API Tokens → Create Token (template Edit Pages, atau custom dengan
    izin Pages:Edit + Account:Read).
  - `CLOUDFLARE_ACCOUNT_ID` — dari Cloudflare Dashboard (sidebar kanan
    halaman Account Overview).
  - Cara pasang: repo GitHub → Settings → Secrets and variables →
    Actions → New repository secret → isi Name + Value → Add secret.
    Nilai token JANGAN PERNAH ditempel di chat — tempel langsung di form
    GitHub tersebut.

## Target prospek default

Diambil dari data agency yang sudah ada (hanya kategori + lokasi, tanpa nama
bisnis): klinik di Bandung (108 bisnis, 81 lead scored). Ubah
`prospect_targets.yaml` untuk menambah kategori/lokasi.
