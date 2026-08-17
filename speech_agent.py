import json
from typing import Optional
from groq import Groq
import config
from survey_engine import Question

_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not set — check your .env file")
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def transcribe(wav_path: str) -> str:
    """Send a .wav file to Groq Whisper, return the transcribed text."""
    client = _get_client()
    with open(wav_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3-turbo",
            response_format="text",
        )
    return str(result).strip()


def classify_response(transcript: str, question: Question) -> Optional[str]:
    """Match a free-text transcript to one of the question's option keys.

    Returns the option_key (e.g. "2") if confident, else None (fallback to
    DTMF).
    """
    if not transcript:
        return None

    options_list = "\n".join(
        f'{key} = "{opt.label}"' for key, opt in question.options.items()
    )

    system_prompt = (
        "You are an intent classifier for a phone survey. "
        "The caller was asked a question and responded in their own words "
        "(possibly in English or Urdu). Match their response to ONE of the "
        "given numbered options based on meaning, not exact wording. "
        "Reply with ONLY a JSON object, nothing else, in this exact format:\n"
        '{"option_key": "<the matching key, or null if unclear/no match>", '
        '"confidence": <0.0 to 1.0>}'
    )

    user_prompt = (
        f"Question: {question.text}\n"
        f"Options:\n{options_list}\n\n"
        f'Caller said: "{transcript}"'
    )

    client = _get_client()
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=100,
    )

    raw = (completion.choices[0].message.content or "").strip()

    try:
        parsed = json.loads(raw)
        option_key = parsed.get("option_key")
        confidence = float(parsed.get("confidence", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    if not option_key or option_key not in question.options:
        return None
    if confidence < 0.6:  # confidence threshold
        return None

    return option_key
def translate_to_english(transcript: str) -> str:
    """Translate any-language transcript to English using the LLM."""
    if not transcript:
        return ""

    system_prompt = (
        "Translate the following text to English. "
        "Reply with ONLY the translated text, nothing else — no quotes, "
        "no explanation. If it is already in English, return it unchanged."
    )

    client = _get_client()
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
        temperature=0.1,
        max_tokens=300,
    )

    return (completion.choices[0].message.content or "").strip()
