import tts
import speech_agent
from survey_engine import Question, Option

# --- Step 1: Fake ek caller ka jawab generate karo (jaise wo bol raha ho) ---
# Isay badal kar test karein: English ya Urdu, alag alag jawab
test_text = "mujhe service bohat pasand aayi, main bohat khush hoon"
test_language = "ur"  # ya "en"

print(f"Generating fake caller audio: '{test_text}'")
audio_path = tts.synthesize(test_text, test_language)
print(f"Audio saved at: {audio_path}\n")

# --- Step 2: Usay transcribe karo (jaise Groq Whisper karega) ---
print("Transcribing...")
transcript = speech_agent.transcribe(str(audio_path))
print(f"Transcript: {transcript}\n")

# --- Step 3: Ek fake Question banao (jaisa q1 hai) taake classify test ho ---
fake_question = Question(
    id=1,
    key="q1",
    position=1,
    text="How satisfied are you with our service?",
    prompt_audio=None,
    input_timeout_ms=15000,
    max_attempts=2,
    options={
        "1": Option(id=1, key="1", label="Very Satisfied", numeric_value=4),
        "2": Option(id=2, key="2", label="Satisfied", numeric_value=3),
        "3": Option(id=3, key="3", label="Dissatisfied", numeric_value=2),
        "4": Option(id=4, key="4", label="Very Dissatisfied", numeric_value=1),
    },
)

# --- Step 4: Classify karo ---
print("Classifying...")
result = speech_agent.classify_response(transcript, fake_question)

if result:
    matched_option = fake_question.options[result]
    print(f"MATCHED: option {result} = {matched_option.label}")
else:
    print("NOT CONFIDENT — DTMF fallback would trigger here")