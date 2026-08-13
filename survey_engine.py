from dataclasses import dataclass
from typing import Optional


@dataclass
class Option:
    id: int
    key: str
    label: str
    numeric_value: Optional[float]


@dataclass
class Question:
    id: int
    key: str
    position: int
    text: str
    prompt_audio: Optional[str]
    input_timeout_ms: int
    max_attempts: int
    options: dict[str, Option]

    @property
    def valid_digits(self) -> str:
        return "".join(sorted(self.options))


@dataclass
class Survey:
    id: int
    key: str
    version: int
    title: str
    intro_text: str
    outro_text: str
    questions: list[Question]


class SurveyEngine:
    """Builds a Survey object graph from the database."""

    def __init__(self, db):
        self.db = db

    def load(self, survey_id: int) -> Survey:
        survey_row = self.db.fetch_survey(survey_id)
        questions = []

        for question_row in self.db.fetch_questions(survey_id):
            options = {
                option_row["option_key"]: Option(
                    id=option_row["id"],
                    key=option_row["option_key"],
                    label=option_row["label"],
                    numeric_value=option_row["numeric_value"],
                )
                for option_row in self.db.fetch_options(question_row["id"])
            }

            questions.append(
                Question(
                    id=question_row["id"],
                    key=question_row["question_key"],
                    position=question_row["position"],
                    text=question_row["text"],
                    prompt_audio=question_row["prompt_audio"],
                    input_timeout_ms=question_row["input_timeout_ms"],
                    max_attempts=question_row["max_attempts"],
                    options=options,
                )
            )

        return Survey(
            id=survey_row["id"],
            key=survey_row["survey_key"],
            version=survey_row["version"],
            title=survey_row["title"],
            intro_text=survey_row["intro_text"] or "",
            outro_text=survey_row["outro_text"] or "",
            questions=questions,
        )