from pathlib import Path
import sys
import time

import config
import tts
import speech_agent
from database import SurveyDatabase
from esl_client import ESLClient
from survey_engine import Question, Survey, SurveyEngine


def select_language(esl: ESLClient, channel_uuid: str) -> str:
    """Play EN + UR prompts, wait for 1 (English) or 2 (Urdu)."""
    en_path = tts.prompt("For English, press 1.", "en")
    ur_path = tts.prompt("اردو کے لیے 2 دبائیں۔", "ur")

    speak(esl, channel_uuid, en_path)
    speak(esl, channel_uuid, ur_path)

    for attempt in range(1, 3):
        digit = esl.ask_question(
            uuid=channel_uuid,
            prompt="",
            var_name=f"lang_select_{attempt}",
            valid_digits="12",
            timeout_ms=10000,
            prompt_seconds=0,
        )
        if digit == "2":
            return "ur"
        if digit == "1":
            return "en"

    print("  No language selected — defaulting to English", flush=True)
    return "en"


def build_prompts(survey: Survey, language: str) -> dict[str, str]:
    """Generate and cache every audio prompt before the call starts."""
    print("Preparing audio prompts...", flush=True)
    prompts: dict[str, str] = {"invalid": tts.prompt(config.TTS_INVALID_TEXT, language)}

    if survey.intro_text:
        prompts["intro"] = tts.prompt(survey.intro_text, language)
    if survey.outro_text:
        prompts["outro"] = tts.prompt(survey.outro_text, language)

    for question in survey.questions:
        prompts[question.key] = (
            question.prompt_audio
            if question.prompt_audio
            else tts.prompt(question.text, language)
        )

    print(f"Audio ready ({len(prompts)} prompts cached)", flush=True)
    return prompts


def speak(esl: ESLClient, uuid: str, path: str | Path) -> None:
    path_obj = Path(path)
    str_path = str(path_obj)
    esl.play(uuid, str_path, tts.duration_seconds(path_obj))


def show_question(index: int, total: int, question: Question) -> None:
    print("\n" + "-" * 55, flush=True)
    print(f"QUESTION {index} of {total}  [{question.key}]", flush=True)
    print(question.text, flush=True)
    for option in question.options.values():
        print(f"    {option.key} - {option.label}", flush=True)
    print("-" * 55, flush=True)


def collect_answer(esl, db, channel_uuid, session_id, question, prompts):
    """
    Ask until valid or attempts run out.
    Accepts EITHER a DTMF keypress OR a spoken answer (via Groq Whisper + LLM).
    DTMF always wins if both happen; voice is only used when no digit came in.
    Returns: (option_key, transcript_or_None, attempts_used, response_ms)
    """
    prompt_path = prompts[question.key]
    prompt_seconds = tts.duration_seconds(prompt_path)

    for attempt in range(1, question.max_attempts + 1):
        if attempt > 1:
            print(f"    Retrying ({attempt}/{question.max_attempts})", flush=True)
            speak(esl, channel_uuid, prompts["invalid"])

        recording_path = tts.fs_path(
            Path(config.RECORDINGS_DIR) / f"{channel_uuid}_{question.key}_{attempt}.wav"
        )

        started = time.perf_counter()

        # Play the question FIRST — recording hasn't started, so this never
        # leaks into the caller's answer.
        speak(esl, channel_uuid, prompt_path)

        # NOW start recording — only the caller's voice from here on.
        try:
            esl.start_recording(channel_uuid, recording_path)
        except RuntimeError:
            pass

        digit = esl.get_digits_only(
            uuid=channel_uuid,
            var_name=f"ans_{question.key}_{attempt}",
            valid_digits=question.valid_digits,
            timeout_ms=question.input_timeout_ms,
        )

        esl.stop_recording(channel_uuid, recording_path)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        # --- Path 1: valid keypad digit — DTMF wins, don't even look at audio ---
        if digit in question.options:
            db.record_attempt(session_id, question.id, attempt, digit, "valid", elapsed_ms)
            return digit, None, attempt, elapsed_ms

        # --- Path 2: no valid digit — try the spoken answer instead ---
        transcript = ""
        option_key = None
        recording_file = Path(recording_path)
        if recording_file.exists() and recording_file.stat().st_size > 1000:
            try:
                transcript = speech_agent.transcribe(recording_path)
                option_key = speech_agent.classify_response(transcript, question)
            except Exception as exc:
                print(f"    Speech agent error: {exc}", flush=True)

        if option_key:
            print(f"    (voice) heard: \"{transcript}\"", flush=True)
            db.record_attempt(session_id, question.id, attempt, transcript, "valid", elapsed_ms)
            return option_key, transcript, attempt, elapsed_ms

        # --- Path 3: neither worked — log and retry ---
        outcome = "invalid" if (digit or transcript) else "no_input"
        db.record_attempt(
            session_id, question.id, attempt, digit or transcript, outcome, elapsed_ms
        )

    return "", None, question.max_attempts, None


def run_survey() -> None:
    Path(config.RECORDINGS_DIR).mkdir(parents=True, exist_ok=True)

    db = SurveyDatabase(config.SQLITE_PATH, config.SCHEMA_PATH)
    db.connect()
    db.init_schema()

    print("=" * 55, flush=True)
    print(f"CALLING: extension {config.TARGET_EXTENSION}", flush=True)
    print("=" * 55, flush=True)

    esl = ESLClient(config.FS_HOST, config.FS_PORT, config.FS_PASSWORD)
    esl.connect()

    channel_uuid = call_id = session_id = None
    answers: list[tuple[str, str, str]] = []
    total = 0

    try:
        channel_uuid = esl.originate(config.TARGET_EXTENSION)
        call_id = db.create_call(channel_uuid, to_number=config.TARGET_EXTENSION)

        language = select_language(esl, channel_uuid)
        print(f"\n[LANGUAGE] Caller selected: {language}", flush=True)

        survey_path = config.SURVEY_PATH if language == "en" else config.SURVEY_PATH_UR
        survey_id = db.import_survey(survey_path)
        survey = SurveyEngine(db).load(survey_id)
        total = len(survey.questions)

        print(f"SURVEY : {survey.key} v{survey.version} — {survey.title}", flush=True)
        print(f"LOADED : {total} question(s)", flush=True)

        prompts = build_prompts(survey, language)
        session_id = db.start_session(survey.id, call_id, total)

        if "intro" in prompts:
            print(f"\n[INTRO] {survey.intro_text}", flush=True)
            speak(esl, channel_uuid, prompts["intro"])

        for index, question in enumerate(survey.questions, start=1):
            show_question(index, total, question)

            try:
                answer_key, transcript, attempts, elapsed_ms = collect_answer(
                    esl, db, channel_uuid, session_id, question, prompts
                )
            except RuntimeError as exc:
                print(f"  CALL ENDED: {exc}", flush=True)
                db.record_response(session_id, question.id, outcome="hangup", attempts_used=1)
                break

            if not answer_key:
                print("  NO ANSWER — recorded as no_input", flush=True)
                db.record_response(
                    session_id, question.id, outcome="no_input", attempts_used=attempts
                )
                continue

            option = question.options[answer_key]
            source = "voice" if transcript else "keypad"
            print(f"  ANSWER ({source}): {answer_key} = {option.label}", flush=True)
            answers.append((question.key, answer_key, option.label))

            db.record_response(
                session_id,
                question.id,
                option_id=option.id,
                raw_input=transcript if transcript else answer_key,
                text_value=transcript or None,
                numeric_value=option.numeric_value,
                outcome="answered",
                attempts_used=attempts,
                response_ms=elapsed_ms,
            )

        if "outro" in prompts and esl.channel_exists(channel_uuid):
            print(f"\n[OUTRO] {survey.outro_text}", flush=True)
            speak(esl, channel_uuid, prompts["outro"])

        if session_id:
            db.finish_session(session_id, "completed" if len(answers) == total else "partial")
        if call_id:
            db.finish_call(call_id, "completed")

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr, flush=True)
        if session_id:
            db.finish_session(session_id, "failed")
        if call_id:
            db.finish_call(call_id, "failed", hangup_cause=str(exc))
        raise

    finally:
        if channel_uuid:
            esl.hangup(channel_uuid)
        esl.close()

        print("\n" + "=" * 55, flush=True)
        print(f"SUMMARY — {len(answers)} of {total} answered", flush=True)
        for question_key, digit, label in answers:
            print(f"  {question_key}: {digit} = {label}", flush=True)
        print("=" * 55, flush=True)

        db.close()


if __name__ == "__main__":
    run_survey()