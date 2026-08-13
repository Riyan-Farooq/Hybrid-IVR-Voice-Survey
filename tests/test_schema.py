import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")

conn = sqlite3.connect(":memory:")
conn.executescript(sql)

tables = [
    r[0]
    for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
]
views = [
    r[0]
    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
]
indexes = [
    r[0]
    for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%' ORDER BY name"
    )
]

print("TABLES :", tables)
print("VIEWS  :", views)
print("INDEXES:", len(indexes))

# Smoke test: definition -> call -> session -> answer -> report
conn.execute("PRAGMA foreign_keys = ON")
conn.execute(
    "INSERT INTO surveys (survey_key, version, title, status) "
    "VALUES ('service_satisfaction', 1, 'Service Satisfaction', 'active')"
)
conn.execute(
    "INSERT INTO questions (survey_id, question_key, position, text) "
    "VALUES (1, 'q1', 1, 'How satisfied are you?')"
)
conn.executemany(
    "INSERT INTO question_options (question_id, option_key, label, numeric_value, position) "
    "VALUES (1, ?, ?, ?, ?)",
    [("1", "Very Satisfied", 4, 1), ("2", "Satisfied", 3, 2), ("3", "Dissatisfied", 2, 3)],
)
conn.execute(
    "INSERT INTO calls (call_uuid, to_number, status) VALUES ('uuid-1', '1000', 'answered')"
)
conn.execute(
    "INSERT INTO survey_sessions (session_uuid, survey_id, call_id, status, questions_total) "
    "VALUES ('sess-1', 1, 1, 'completed', 1)"
)
conn.execute(
    "INSERT INTO responses (session_id, question_id, option_id, raw_input, numeric_value) "
    "VALUES (1, 1, 2, '2', 3)"
)
conn.executemany(
    "INSERT INTO response_attempts (session_id, question_id, attempt_no, raw_input, outcome) "
    "VALUES (1, 1, ?, ?, ?)",
    [(1, "", "no_input"), (2, "2", "valid")],
)
conn.commit()

print("ANSWERS       :", conn.execute("SELECT survey_key, question_key, option_label, numeric_value FROM v_answers").fetchall())
print("DISTRIBUTION  :", conn.execute("SELECT option_key, response_count FROM v_option_distribution").fetchall())
print("SCORES        :", conn.execute("SELECT question_key, avg_score FROM v_question_scores").fetchall())
print("COMPLETION    :", conn.execute("SELECT survey_key, sessions, completed, completion_rate FROM v_survey_completion").fetchall())
print("FRICTION      :", conn.execute("SELECT question_key, total_attempts, friction_rate FROM v_question_friction").fetchall())

conn.close()
print("Schema OK")
