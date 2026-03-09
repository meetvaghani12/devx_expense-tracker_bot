"""
Voice message handler.
Downloads Telegram voice note → transcribes via Groq Whisper → pipes to NL handler.
"""
import io
import logging

from telegram import Update
from telegram.ext import ContextTypes

from ai.transcriber import transcribe, TranscriptionError

logger = logging.getLogger(__name__)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for voice messages (OGG/OPUS from Telegram)."""
    await update.message.reply_text("🎙️ Listening...")

    voice = update.message.voice
    tg_file = await voice.get_file()

    # Download into memory — no disk writes
    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    audio_bytes = buf.getvalue()

    try:
        transcribed = await transcribe(audio_bytes, mime_type="audio/ogg")
    except TranscriptionError as e:
        logger.warning(f"Voice transcription failed: {e}")
        await update.message.reply_text(
            "Sorry, I couldn't understand that audio. Please try again or type your message."
        )
        return

    # Echo back so user can verify
    await update.message.reply_text(
        f"🎙️ I heard: _{transcribed}_",
        parse_mode="Markdown",
    )

    # Process through the NL pipeline directly (avoid mutating read-only update.message.text)
    from bot.handlers.nl import process_nl_text
    try:
        await process_nl_text(transcribed, update, context)
    except Exception as e:
        logger.error(f"NL pipeline failed for voice: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ NL error: `{type(e).__name__}: {e}`\n\nPlease try typing your message instead.",
            parse_mode="Markdown",
        )
