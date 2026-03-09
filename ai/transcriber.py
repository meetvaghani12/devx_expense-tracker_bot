"""
Voice transcription using Groq's Whisper large-v3.
Free tier: 2000 requests/day, 20 RPM.
"""
import io
import logging
from groq import AsyncGroq
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=GROQ_API_KEY)
    return _client


class TranscriptionError(Exception):
    pass


async def transcribe(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcribes audio bytes using Groq Whisper large-v3.
    Returns plain text string.
    Raises TranscriptionError on failure or empty result.
    """
    client = _get_client()
    try:
        file_tuple = ("voice.ogg", io.BytesIO(audio_bytes), mime_type)
        transcription = await client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=file_tuple,
            response_format="text",
            language="en",
        )
        text = transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
        if len(text) < 2:
            raise TranscriptionError("Empty transcription result")
        logger.info(f"Whisper transcribed: {text[:80]}")
        return text
    except TranscriptionError:
        raise
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        raise TranscriptionError(str(e))
