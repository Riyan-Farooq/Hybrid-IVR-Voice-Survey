import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Project ki root directory jahan config.py pari hui hai
BASE_DIR = Path(__file__).resolve().parent

# FreeSWITCH Event Socket (ESL)
FS_HOST = os.getenv("FS_HOST", "127.0.0.1")
FS_PORT = int(os.getenv("FS_PORT", "8021"))
FS_PASSWORD = os.getenv("FS_PASSWORD", "ClueCon")

# Who to call (MicroSIP extension)
TARGET_EXTENSION = os.getenv("TARGET_EXTENSION", "1000")
CALLER_ID = os.getenv("CALLER_ID", "Survey")

# Database: "sqlite" or "mysql"
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite")
SQLITE_PATH = os.getenv("SQLITE_PATH", str(BASE_DIR / "survey.db"))

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "survey_poc"),
}

# Paths made dynamically absolute
SURVEY_PATH = os.getenv("SURVEY_PATH", str(BASE_DIR / "surveys" / "sample_survey.json"))
SURVEY_PATH_UR = os.getenv("SURVEY_PATH_UR", str(BASE_DIR / "surveys" / "sample_survey_ur.json"))
SCHEMA_PATH = os.getenv("SCHEMA_PATH", str(BASE_DIR / "db" / "schema.sql"))
AUDIO_CACHE_DIR = os.getenv("AUDIO_CACHE_DIR", str(BASE_DIR / "audio" / "cache"))

# Text-to-speech
TTS_VOICE_HINT = os.getenv("TTS_VOICE_HINT", "zira")
TTS_RATE = int(os.getenv("TTS_RATE", "165"))
TTS_INVALID_TEXT = os.getenv(
    "TTS_INVALID_TEXT",
    "Sorry, that is not a valid choice. Please try again.",
)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", str(BASE_DIR / "recordings"))