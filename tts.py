import hashlib
import wave
from pathlib import Path

import pyttsx3
from gtts import gTTS
from pydub import AudioSegment

import config


def _cache_path(text: str, language: str = "en") -> Path:
    key = f"{language}|{config.TTS_VOICE_HINT}|{config.TTS_RATE}|{text}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return Path(config.AUDIO_CACHE_DIR) / language / f"{digest}.wav"


def _select_voice(engine) -> None:
    hint = (config.TTS_VOICE_HINT or "").lower()
    if not hint:
        return
    for voice in engine.getProperty("voices"):
        if hint in voice.name.lower() or hint in voice.id.lower():
            engine.setProperty("voice", voice.id)
            return


def _synthesize_en(text: str, path: Path) -> None:
    # A fresh engine per file: SAPI5 misbehaves when one is reused.
    engine = pyttsx3.init()
    engine.setProperty("rate", config.TTS_RATE)
    _select_voice(engine)
    engine.save_to_file(text, str(path))
    engine.runAndWait()
    engine.stop()


def _synthesize_ur(text: str, path: Path) -> None:
    # gTTS only writes mp3 — FreeSWITCH wants wav, so convert after.
    mp3_path = path.with_suffix(".mp3")
    gTTS(text=text, lang="ur").save(str(mp3_path))
    AudioSegment.from_mp3(mp3_path).export(path, format="wav")
    mp3_path.unlink()


def synthesize(text: str, language: str = "en") -> Path:
    """Return a cached WAV for this text, generating it on first use."""
    path = _cache_path(text, language)
    if path.exists() and path.stat().st_size > 0:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    if language == "ur":
        _synthesize_ur(text, path)
    else:
        _synthesize_en(text, path)

    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"TTS produced no audio for: {text[:60]!r}")

    return path


def duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def fs_path(path: Path) -> str:
    """Absolute path in the form FreeSWITCH expects on Windows."""
    return str(Path(path).resolve()).replace("\\", "/")


def prompt(text: str, language: str = "en") -> str:
    """Text -> playable FreeSWITCH file path."""
    return fs_path(synthesize(text, language))


def list_voices() -> list[str]:
    engine = pyttsx3.init()
    names = [voice.name for voice in engine.getProperty("voices")]
    engine.stop()
    return names