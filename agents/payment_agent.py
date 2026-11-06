"""
Fase 4: Operasional — kirim barcode QRIS/DANA, konfirmasi pembayaran MANUAL,
lalu deploy preview + domain.

CATATAN ARSITEKTUR (pola yang sama seperti marketing & website agent):
bayar itu ASYNC — barcode dikirim, lalu sistem HARUS nunggu klien transfer
(bisa jam/hari kemudian), dan menunggu KAMU (owner) konfirmasi manual bahwa
dana sudah benar-benar masuk. Jadi:

- `run(state)` cuma kirim gambar barcode QRIS/DANA statis ke klien, status
  jadi INVOICED, lalu berhenti (orchestrator sudah didesain berhenti
  setelah node payment — lihat _route_after_payment di core/orchestrator.py).
- TIDAK ADA polling otomatis ke payment gateway manapun. Kamu yang cek
  manual (notifikasi DANA kamu sendiri, atau klien japri WA/email
  konfirmasi), baru kamu ketik command di bot Telegram, misalnya:
  `/sudah_bayar <project_id>` — itu yang memicu `confirm_payment()` di
  bawah untuk lanjut ke deploy preview.

Alasan pindah dari Midtrans ke QRIS/DANA manual: lebih sederhana, tidak
perlu daftar akun merchant / payment gateway pihak ketiga. Trade-off: tidak
ada notifikasi otomatis saat dana masuk, makanya konfirmasi harus manual
oleh owner — ini juga jadi pengaman supaya sistem tidak pernah keliru kasih
link produk ke klien yang belum bayar.

HOSTING & DOMAIN — dua tahap terpisah dengan sifat berbeda:
1. `deploy_to_cf_pages()` — jalan begitu KAMU konfirmasi pembayaran lewat
   bot (bukan lagi otomatis lewat webhook payment gateway). Website
   langsung live di URL *.pages.dev sebagai preview untuk klien
   (Cloudflare Pages, gratis, bandwidth unlimited).
2. `attach_domain()` — SEMI-OTOMATIS, dipicu MANUAL lewat command Telegram
   (misal /pasang_domain <project_id> <domain>) setelah klien oke dengan
   preview DAN kamu beli & siapkan domainnya sendiri. Bagian ini nge-set
   custom_domain di sisi Cloudflare Pages, tapi pointing DNS di
   registrar/provider domain kamu tetap langkah manual di luar sistem —
   attach_domain() kasih instruksi record DNS yang perlu diisi.

Alasan dipisah: pembelian domain menyangkut uang asli & pilihan registrar
yang beragam (belum ada API terpadu yang cocok untuk semua kasus), jadi
lebih aman kamu yang pegang kendali beli, sistem cuma bantu setup teknis
begitu domainnya sudah di tangan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import requests

from config.settings import (
    DANA_QRIS_IMAGE_PATH,
    DEFAULT_INVOICE_DUE_DAYS,
    STAGING_DIR,
)
from core.cloudflare import attach_custom_domain, deploy_site
from core.database import get_business, get_project, save_invoice, save_message, save_project
from core.packages import get_package
from core.whatsapp import send_image, send_text
from core.state import PipelineState
from models.schemas import Invoice, InvoiceStatus, Message, Project, ProjectStatus

logger = logging.getLogger("payment_agent")


def _notify(business, isi: str) -> bool:
    """Kirim teks ke klien lewat WhatsApp (balasan/ke klien yang sudah deal, bukan pesan dingin)."""
    return send_text(business.nomor_wa, isi, cold=False)


def _notify_image(business, image_path: str, caption: str) -> bool:
    """Kirim gambar barcode QRIS/DANA ke klien lewat WhatsApp."""
    return send_image(business.nomor_wa, image_path, caption, cold=False)


# ---------------------------------------------------------------------------
# Invoice & kirim barcode
# ---------------------------------------------------------------------------

def create_invoice(project: Project) -> Invoice:
    package_spec = get_package(project.brief.get("paket"))
    nominal = project.brief.get("harga_override") or package_spec.get("harga_estimasi")

    if not nominal:
        raise ValueError(
            f"Nominal invoice belum ada. Isi 'harga_estimasi' di config/packages.yaml "
            f"untuk paket '{package_spec['id']}', atau set brief['harga_override'] manual."
        )

    invoice = Invoice(
        project_id=project.id,
        nominal=int(nominal),
        jatuh_tempo=datetime.utcnow() + timedelta(days=DEFAULT_INVOICE_DUE_DAYS),
        status=InvoiceStatus.DRAFT,
    )
    save_invoice(invoice)
    return invoice


def send_invoice(invoice: Invoice, business_id: str, business_nama: str) -> Invoice:
    """Kirim ke klien DUA gambar lewat WhatsApp: (1) screenshot hasil website
    (hanya gambar, TANPA link staging, supaya website yang bisa diklik baru
    ada setelah bayar), lalu (2) barcode QRIS/DANA statis dengan nominal
    dan batas waktu di caption."""
    business = get_business(business_id)
    project = get_project(invoice.project_id)
    if business is None or project is None:
        raise ValueError("Bisnis/project untuk invoice tidak ditemukan")
    if not project.screenshot_path:
        raise ValueError("Screenshot website belum ada, barcode tidak dikirim tanpa preview")

    preview_caption = (
        f"Halo, ini rancangan website untuk {business_nama} ya \U0001F64C "
        f"Kalau cocok, lanjut ke pembayaran di pesan berikutnya."
    )
    if not _notify_image(business, project.screenshot_path, preview_caption):
        raise ValueError("Screenshot gagal terkirim ke klien (cek nomor WA / bridge WA)")
    save_message(Message(business_id=business_id, isi=preview_caption, agent="payment_agent", arah="out"))

    pay_caption = (
        f"Untuk lanjut, silakan transfer Rp{invoice.nominal:,} via QRIS/DANA "
        f"(scan barcode ini), paling lambat {invoice.jatuh_tempo.strftime('%d %b %Y')}. "
        f"Setelah transfer, kabari kami di sini ya. Website langsung kami online-kan begitu pembayaran kami terima."
    ).replace(",", ".")
    if not _notify_image(business, DANA_QRIS_IMAGE_PATH, pay_caption):
        raise ValueError("Barcode gagal terkirim ke klien (cek nomor WA / bridge WA)")
    save_message(Message(business_id=business_id, isi=pay_caption, agent="payment_agent", arah="out"))

    invoice.status = InvoiceStatus.SENT
    save_invoice(invoice)
    return invoice


def deploy_to_cf_pages(project: Project) -> tuple[str, str]:
    """Deploy isi storage/staging/{id}/site ke Cloudflare Pages.
    Bikin (atau reuse) project `agency-{id}`. Return (project_name, live_url)."""
    site_dir = STAGING_DIR / project.id / "site"
    project_name = project.cf_pages_project or f"agency-{project.id}"
    live_url = deploy_site(str(site_dir), project_name)
    return project_name, live_url


def attach_domain(project_id: str, domain: str) -> dict:
    """
    Dipanggil MANUAL setelah klien oke dengan preview DAN kamu beli domain
    sendiri (belum otomatis lewat bot). Set custom_domain di Cloudflare
    Pages untuk project ini, lalu return instruksi DNS yang perlu kamu isi
    di registrar/DNS provider domainnya.
    """
    project = get_project(project_id)
    if project is None:
        raise ValueError(f"Project {project_id} tidak ditemukan")
    if not project.cf_pages_project:
        raise ValueError("Project belum di-deploy ke Cloudflare Pages (belum ada cf_pages_project)")

    result = attach_custom_domain(project.cf_pages_project, domain)
    project.custom_domain = domain
    save_project(project)
    return result


# ---------------------------------------------------------------------------
# Konfirmasi manual (dipicu command bot Telegram, GANTI check_pending_payments)
# ---------------------------------------------------------------------------

def confirm_payment(project_id: str) -> dict:
    """
    Dipanggil HANYA oleh owner lewat command bot Telegram (misal
    `/sudah_bayar <project_id>`), setelah owner yakin sendiri dana sudah
    masuk (lihat notifikasi DANA atau konfirmasi klien via WA/email).

    Ini GANTI total fungsi check_pending_payments() yang lama (polling
    otomatis ke Midtrans) — di sini tidak ada pengecekan status otomatis
    ke payment gateway manapun, murni dipicu keputusan manusia supaya
    tidak pernah salah kasih link produk ke klien yang belum bayar.

    Begitu dipanggil: invoice & project ditandai PAID, lalu langsung
    deploy ke Netlify sebagai preview gratis untuk klien.
    """
    invoice = _get_invoice_by_project(project_id)
    if invoice is None:
        raise ValueError(f"Invoice untuk project {project_id} tidak ditemukan")
    if invoice.status == InvoiceStatus.PAID:
        raise ValueError(f"Invoice project {project_id} sudah dikonfirmasi lunas sebelumnya")

    invoice.status = InvoiceStatus.PAID
    save_invoice(invoice)

    project = get_project(project_id)
    if project is None:
        raise ValueError(f"Project {project_id} tidak ditemukan")

    project.status = ProjectStatus.PAID
    save_project(project)

    site_id, live_url = deploy_to_cf_pages(project)
    project.cf_pages_project = site_id
    project.live_url = live_url
    project.status = ProjectStatus.PUBLISHED
    save_project(project)

    business = get_business(project.business_id)
    if business is not None:
        isi = f"Pembayaran diterima, terima kasih! Preview website {business.nama} sudah live: {live_url}"
        if _notify(business, isi):
            save_message(Message(business_id=business.id, isi=isi, agent="payment_agent", arah="out"))

    return {"project_id": project.id, "live_url": live_url, "status": project.status.value}


def _get_invoice_by_project(project_id: str) -> Invoice | None:
    from core.database import get_conn  # local import, sama seperti query lintas-invoice lain

    with get_conn() as conn:
        rows = conn.execute("SELECT data FROM invoices").fetchall()

    candidates = [Invoice.model_validate_json(row["data"]) for row in rows]
    candidates = [inv for inv in candidates if inv.project_id == project_id]
    if not candidates:
        return None
    # ambil invoice terbaru kalau lebih dari satu
    return max(candidates, key=lambda inv: inv.created_at)


def send_reminders() -> int:
    from core.database import get_conn

    with get_conn() as conn:
        rows = conn.execute("SELECT data FROM invoices").fetchall()

    now = datetime.utcnow()
    sent = 0
    for row in rows:
        invoice = Invoice.model_validate_json(row["data"])
        if invoice.status != InvoiceStatus.SENT:
            continue
        if invoice.jatuh_tempo > now:
            continue  # belum lewat jatuh tempo

        project = get_project(invoice.project_id)
        if project is None:
            continue
        business = get_business(project.business_id)
        if business is None:
            continue

        isi = f"Reminder: pembayaran untuk {business.nama} sudah lewat batas waktu, mohon segera diselesaikan ya."
        if _notify(business, isi):
            save_message(Message(business_id=business.id, isi=isi, agent="payment_agent", arah="out"))
            sent += 1

    return sent


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(state: PipelineState) -> PipelineState:
    project_id = state.get("project_id")
    if not project_id:
        state["error"] = "payment: project_id tidak ada di state"
        return state

    project = get_project(project_id)
    if project is None:
        state["error"] = f"payment: project {project_id} tidak ditemukan"
        return state

    business = get_business(project.business_id)
    if business is None:
        state["error"] = f"payment: business {project.business_id} tidak ditemukan"
        return state

    try:
        invoice = create_invoice(project)
        send_invoice(invoice, business.id, business.nama)
    except (ValueError, requests.RequestException) as exc:
        state["error"] = f"payment: {exc}"
        return state

    project.status = ProjectStatus.INVOICED
    save_project(project)

    state["status"] = "invoiced"
    return state
