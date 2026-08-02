import pytest
from pytest import MonkeyPatch

from app.services import audio_transcription
from app.services.audio_transcription import TRANSCRIPTION_MODEL, transcribe_audio


class FakeTranscription:
    text = " Texto transcrito "


class FakeTranscriptions:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> FakeTranscription:
        self.kwargs = kwargs
        return FakeTranscription()


class FakeAudio:
    def __init__(self) -> None:
        self.transcriptions = FakeTranscriptions()


class FakeAsyncOpenAI:
    instance: "FakeAsyncOpenAI | None" = None

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.audio = FakeAudio()
        FakeAsyncOpenAI.instance = self


@pytest.mark.anyio
async def test_transcribe_audio_uses_gpt_4o_transcribe(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(audio_transcription.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(audio_transcription, "AsyncOpenAI", FakeAsyncOpenAI)

    text = await transcribe_audio(
        content=b"audio",
        filename="recording.webm",
        content_type="audio/webm",
    )

    assert text == "Texto transcrito"
    assert FakeAsyncOpenAI.instance is not None
    assert FakeAsyncOpenAI.instance.kwargs == {"api_key": "test-key"}
    assert FakeAsyncOpenAI.instance.audio.transcriptions.kwargs == {
        "model": TRANSCRIPTION_MODEL,
        "file": ("recording.webm", b"audio", "audio/webm"),
    }


@pytest.mark.anyio
async def test_transcribe_audio_requires_openai_api_key(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(audio_transcription.settings, "OPENAI_API_KEY", "")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await transcribe_audio(
            content=b"audio",
            filename="recording.webm",
            content_type="audio/webm",
        )
