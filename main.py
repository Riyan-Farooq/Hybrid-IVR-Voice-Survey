from pathlib import Path
import sys
import time

import config
import tts
from database import SurveyDatabase
from esl_client import ESLClient
from survey_engine import Question, Survey, SurveyEngine
from pathlib import Path


def build_prompts(survey: Survey) -> dict[str, str]:
    """Generate and cache every audio prompt before the call starts."""
    print("Preparing audio prompts...", flush=True)
    prompts: dict[str, str] = {"invalid": tts.prompt(config.TTS_INVALID_TEXT)}

    if survey.intro_text:
        prompts["intro"] = tts.prompt(survey.intro_text)
    if survey.outro_text:
        prompts["outro"] = tts.prompt(survey.outro_text)

    for question in survey.questions:
        # A recorded file, when supplied, wins over synthesized speech.
        prompts[question.key] = (
            question.prompt_audio
            if question.prompt_audio
            else tts.prompt(question.text)
        )

    print(f"Audio ready ({len(prompts)} prompts cached)", flush=True)
    return prompts
   


def speak(esl: ESLClient, uuid: str, path: str | Path) -> None:
    path_obj = Path(path)       # tts ke liye Path object
    str_path = str(path_obj)     # esl.play ke liye String

    # tts.duration_seconds ko Path object pass karein aur esl.play ko str
    esl.play(uuid, str_path, tts.duration_seconds(path_obj))

def show_question(index: int, total: int, question: Question) -> None:
    print("\n" + "-" * 55, flush=True)
    print(f"QUESTION {index} of {total}  [{question.key}]", flush=True)
    print(question.text, flush=True)
    for option in question.options.values():
        print(f"    {option.key} - {option.label}", flush=True)
    print("-" * 55, flush=True)


def collect_answer(esl, db, channel_uuid, session_id, question, prompts):
    """Ask until valid or attempts run out. Every attempt is recorded."""
    prompt_path = prompts[question.key]
    prompt_seconds = tts.duration_seconds(prompt_path)

    for attempt in range(1, question.max_attempts + 1):
        if attempt > 1:
            print(f"    Retrying ({attempt}/{question.max_attempts})", flush=True)
            speak(esl, channel_uuid, prompts["invalid"])

        started = time.perf_counter()
        digit = esl.ask_question(
            uuid=channel_uuid,
            prompt=prompt_path,
            var_name=f"ans_{question.key}_{attempt}",
            valid_digits=question.valid_digits,
            timeout_ms=question.input_timeout_ms,
            prompt_seconds=prompt_seconds,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        valid = digit in question.options
        db.record_attempt(
            session_id,
            question.id,
            attempt,
            digit,
            "valid" if valid else ("invalid" if digit else "no_input"),
            elapsed_ms,
        )

        if valid:
            return digit, attempt, elapsed_ms

    return "", question.max_attempts, None

def run_survey() -> None:
    db = SurveyDatabase(config.SQLITE_PATH, config.SCHEMA_PATH)
    db.connect()
    db.init_schema()

    survey_id = db.import_survey(config.SURVEY_PATH)
    survey = SurveyEngine(db).load(survey_id)
    total = len(survey.questions)

    print("=" * 55, flush=True)
    print(f"SURVEY : {survey.key} v{survey.version} — {survey.title}", flush=True)
    print(f"CALLING: extension {config.TARGET_EXTENSION}", flush=True)
    print(f"LOADED : {total} question(s)", flush=True)
    print("=" * 55, flush=True)

    prompts = build_prompts(survey)

    esl = ESLClient(config.FS_HOST, config.FS_PORT, config.FS_PASSWORD)
    esl.connect()

    channel_uuid = call_id = session_id = None
    answers: list[tuple[str, str, str]] = []

    try:
        channel_uuid = esl.originate(config.TARGET_EXTENSION)
        call_id = db.create_call(channel_uuid, to_number=config.TARGET_EXTENSION)
        session_id = db.start_session(survey.id, call_id, total)

        if "intro" in prompts:
            print(f"\n[INTRO] {survey.intro_text}", flush=True)
            speak(esl, channel_uuid, prompts["intro"])

        for index, question in enumerate(survey.questions, start=1):
            show_question(index, total, question)

            try:
                digit, attempts, elapsed_ms = collect_answer(
                    esl, db, channel_uuid, session_id, question, prompts
                )
            except RuntimeError as exc:
                print(f"  CALL ENDED: {exc}", flush=True)
                db.record_response(
                    session_id, question.id, outcome="hangup", attempts_used=1
                )
                break

            if not digit:
                print("  NO ANSWER — recorded as no_input", flush=True)
                db.record_response(
                    session_id,
                    question.id,
                    outcome="no_input",
                    attempts_used=attempts,
                )
                continue

            option = question.options[digit]
            print(f"  ANSWER: {digit} = {option.label}", flush=True)
            answers.append((question.key, digit, option.label))

            db.record_response(
                session_id,
                question.id,
                option_id=option.id,
                raw_input=digit,
                numeric_value=option.numeric_value,
                outcome="answered",
                attempts_used=attempts,
                response_ms=elapsed_ms,
            )

        if "outro" in prompts and esl.channel_exists(channel_uuid):
            print(f"\n[OUTRO] {survey.outro_text}", flush=True)
            speak(esl, channel_uuid, prompts["outro"])

        if session_id:
            db.finish_session(
                session_id, "completed" if len(answers) == total else "partial"
            )
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