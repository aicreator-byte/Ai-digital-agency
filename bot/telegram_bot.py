"""
Bot Telegram untuk approval interaktif. Pakai python-telegram-bot v21+.

Alur:
- orchestrator/preview_agent panggil `send_review_request()` waktu project
  masuk status STAGED -> kirim screenshot + staging_url + 3 tombol inline.
- User tekan tombol -> callback_handler() dipanggil -> delegasi ke
  bot/pipeline_state.py buat proses transisi status.
- Kalau user pilih "Revisi", bot minta reply teks catatan revisi dulu
  sebelum benar-benar transisi (lihat `_PENDING_REVISION`).
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID
from bot.pipeline_state import handle_approve, handle_reject, handle_revision
from agents.payment_agent import confirm_payment

logger = logging.getLogger("telegram_bot")

# project_id yang lagi nunggu user ngetik catatan revisi (in-memory, single-operator)
_PENDING_REVISION: dict[int, str] = {}


def _review_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{project_id}"),
        InlineKeyboardButton("✏️ Revisi", callback_data=f"revise:{project_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:{project_id}"),
    ]])


async def send_review_request(
    app: Application, project_id: str, business_nama: str,
    staging_url: str, screenshot_path: str,
) -> None:
    caption = (
        f"Website untuk *{business_nama}* sudah siap direview.\n"
        f"Preview: {staging_url}"
    )
    with open(screenshot_path, "rb") as photo:
        await app.bot.send_photo(
            chat_id=TELEGRAM_OWNER_CHAT_ID,
            photo=photo,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=_review_keyboard(project_id),
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action, project_id = query.data.split(":", 1)

    if action == "approve":
        p = handle_approve(project_id)
        await query.edit_message_caption(caption=f"✅ Disetujui. Status: {p.status.value}")

    elif action == "revise":
        _PENDING_REVISION[query.from_user.id] = project_id
        await query.message.reply_text("Kirim catatan revisinya (balas pesan ini dengan teks).")

    elif action == "reject":
        p = handle_reject(project_id)
        await query.edit_message_caption(caption=f"❌ Ditolak. Status: {p.status.value}")


async def revision_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    project_id = _PENDING_REVISION.pop(user_id, None)
    if project_id is None:
        return  # bukan lagi nunggu catatan revisi, abaikan

    catatan = update.message.text
    p = handle_revision(project_id, catatan)

    if p.status.value == "stuck":
        await update.message.reply_text(
            f"⚠️ Revisi ke-{p.revision_count} melebihi batas ({p.max_revisions}). "
            "Perlu review manual, bukan auto-lanjut."
        )
    else:
        await update.message.reply_text(
            f"Catatan diterima, dikirim balik ke website builder. Status: {p.status.value}"
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("AI Digital Agency bot aktif.")


async def sudah_bayar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /sudah_bayar <project_id> — dipakai HANYA oleh owner, setelah owner
    yakin sendiri dana QRIS/DANA sudah masuk (cek notifikasi sendiri atau
    konfirmasi klien via WA/email). Tidak ada pengecekan otomatis ke
    payment gateway manapun — ini satu-satunya pemicu sistem lanjut
    deploy preview, sengaja dibuat manual supaya tidak pernah salah kasih
    link produk ke klien yang belum bayar.
    """
    if not context.args:
        await update.message.reply_text("Format: /sudah_bayar <project_id>")
        return

    project_id = context.args[0]
    try:
        result = confirm_payment(project_id)
    except ValueError as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        return

    await update.message.reply_text(
        f"✅ Pembayaran dikonfirmasi. Preview sudah live: {result['live_url']}"
    )


def build_bot() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("sudah_bayar", sudah_bayar_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, revision_note_handler))
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot_app = build_bot()
    bot_app.run_polling()
