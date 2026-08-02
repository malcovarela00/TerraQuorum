from openai import AsyncOpenAI

from app.core.config import settings

TRANSCRIPTION_MODEL = "gpt-4o-transcribe"


async def transcribe_audio(
    *, content: bytes, filename: str, content_type: str | None
) -> str:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required to transcribe audio.")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    transcription = await client.audio.transcriptions.create(
        model=TRANSCRIPTION_MODEL,
        file=(filename, content, content_type or "application/octet-stream"),
    )
    text = transcription.text.strip()
    if not text:
        raise ValueError("OpenAI returned an empty transcription.")
    return text
