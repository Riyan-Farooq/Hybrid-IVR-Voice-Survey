import json
import sqlite3
import uuid as uuidlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _fmt(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def utc_now() -> str:
    return _fmt(datetime.now(timezone.utc))


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


class SurveyDatabase:
   
    def __init__(self, db_path: str = "survey.db", schema_path: str = "db/schema.sql"):
        # Resolve path relative to project root if it's relative
        self.db_path = Path(db_path).resolve()
        self.schema_path = Path(schema_path).resolve()
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    def connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def init_schema(self) -> None:
        self.conn.executescript(self.schema_path.read_text(encoding="utf-8"))
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ---------------------------------------------------------- definition

    def import_survey(self, json_path: str) -> int:
        """Load a survey JSON into the database. Safe to call repeatedly."""
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        survey_key = data["survey_id"]
        version = int(data.get("version", 1))

        existing = self.conn.execute(
            "SELECT id FROM surveys WHERE survey_key = ? AND version = ?",
            (survey_key, version),
        ).fetchone()
        if existing:
            return existing["id"]

        cursor = self.conn.execute(
            "INSERT INTO surveys (survey_key, version, title, description, locale,"
            " intro_text, outro_text, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
            (
                survey_key,
                version,
                data.get("title", survey_key),
                data.get("description"),
                data.get("locale", "en-US"),
                data.get("intro"),
                data.get("outro"),
            ),
        )
        survey_id = cursor.lastrowid

        for position, question in enumerate(data["questions"], start=1):
            question_cursor = self.conn.execute(
                "INSERT INTO questions (survey_id, question_key, position, text,"
                " prompt_audio, question_type, input_timeout_ms, max_attempts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    survey_id,
                    question["id"],
                    position,
                    question["text"],
                    question.get("prompt_audio"),
                    question.get("type", "dtmf_choice"),
                    int(question.get("timeout_ms", 15000)),
                    int(question.get("max_attempts", 3)),
                ),
            )
            question_id = question_cursor.lastrowid

            options = question["options"].items()
            for option_position, (option_key, option) in enumerate(options, start=1):
                if isinstance(option, dict):
                    label = option["label"]
                    numeric_value = option.get("value")
                else:
                    label = option
                    numeric_value = None

                self.conn.execute(
                    "INSERT INTO question_options (question_id, option_key, label,"
                    " numeric_value, position) VALUES (?, ?, ?, ?, ?)",
                    (question_id, option_key, label, numeric_value, option_position),
                )

        self.conn.commit()
        return survey_id

    def fetch_survey(self, survey_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM surveys WHERE id = ?", (survey_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"No survey with id {survey_id}")
        return row

    def fetch_questions(self, survey_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM questions WHERE survey_id = ? ORDER BY position",
            (survey_id,),
        ).fetchall()

    def fetch_options(self, question_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM question_options WHERE question_id = ? ORDER BY position",
            (question_id,),
        ).fetchall()

    # ---------------------------------------------------------- execution

    def create_call(
        self,
        call_uuid: str,
        to_number: str,
        from_number: Optional[str] = None,
        status: str = "answered",
        contact_id: Optional[int] = None,
        campaign_id: Optional[int] = None,
    ) -> int:
        now = utc_now()
        cursor = self.conn.execute(
            "INSERT INTO calls (call_uuid, campaign_id, contact_id, direction,"
            " from_number, to_number, status, initiated_at, answered_at)"
            " VALUES (?, ?, ?, 'outbound', ?, ?, ?, ?, ?)",
            (
                call_uuid,
                campaign_id,
                contact_id,
                from_number,
                to_number,
                status,
                now,
                now if status == "answered" else None,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_call(
        self, call_id: int, status: str, hangup_cause: Optional[str] = None
    ) -> None:
        row = self.conn.execute(
            "SELECT initiated_at, answered_at FROM calls WHERE id = ?", (call_id,)
        ).fetchone()

        ended = datetime.now(timezone.utc)
        duration = talk = None
        if row:
            duration = int((ended - _parse(row["initiated_at"])).total_seconds())
            if row["answered_at"]:
                talk = int((ended - _parse(row["answered_at"])).total_seconds())

        self.conn.execute(
            "UPDATE calls SET status = ?, hangup_cause = ?, ended_at = ?,"
            " duration_seconds = ?, talk_seconds = ? WHERE id = ?",
            (status, hangup_cause, _fmt(ended), duration, talk, call_id),
        )
        self.conn.commit()

    def start_session(
        self,
        survey_id: int,
        call_id: int,
        questions_total: int,
        contact_id: Optional[int] = None,
        channel: str = "voice",
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO survey_sessions (session_uuid, survey_id, call_id, contact_id,"
            " channel, status, questions_total, started_at)"
            " VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?)",
            (
                str(uuidlib.uuid4()),
                survey_id,
                call_id,
                contact_id,
                channel,
                questions_total,
                utc_now(),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_session(self, session_id: int, status: str) -> None:
        answered = self.conn.execute(
            "SELECT COUNT(*) AS n FROM responses"
            " WHERE session_id = ? AND outcome = 'answered'",
            (session_id,),
        ).fetchone()["n"]

        self.conn.execute(
            "UPDATE survey_sessions SET status = ?, questions_answered = ?,"
            " completed_at = ? WHERE id = ?",
            (status, answered, utc_now(), session_id),
        )
        self.conn.commit()

    # ---------------------------------------------------------- results

    def record_attempt(
        self,
        session_id: int,
        question_id: int,
        attempt_no: int,
        raw_input: str,
        outcome: str,
        response_ms: Optional[int] = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO response_attempts (session_id, question_id,"
            " attempt_no, raw_input, outcome, response_ms, occurred_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                question_id,
                attempt_no,
                raw_input,
                outcome,
                response_ms,
                utc_now(),
            ),
        )
        self.conn.commit()

    def record_response(
        self,
        session_id: int,
        question_id: int,
        option_id: Optional[int] = None,
        raw_input: Optional[str] = None,
        numeric_value: Optional[float] = None,
        outcome: str = "answered",
        attempts_used: int = 1,
        response_ms: Optional[int] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO responses (session_id, question_id, option_id, raw_input,"
            " numeric_value, outcome, attempts_used, response_ms, answered_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(session_id, question_id) DO UPDATE SET"
            " option_id = excluded.option_id, raw_input = excluded.raw_input,"
            " numeric_value = excluded.numeric_value, outcome = excluded.outcome,"
            " attempts_used = excluded.attempts_used,"
            " response_ms = excluded.response_ms, answered_at = excluded.answered_at",
            (
                session_id,
                question_id,
                option_id,
                raw_input,
                numeric_value,
                outcome,
                attempts_used,
                response_ms,
                utc_now(),
            ),
        )
        self.conn.commit()