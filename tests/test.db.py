import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SurveyDatabase

db = SurveyDatabase("survey.db")
db.connect()
db.init_schema()
db.start_call("test-uuid-001", "user_001", "service_satisfaction_v1")
db.save_response("test-uuid-001", "service_satisfaction_v1", "q1", "2")
db.finish_call("test-uuid-001")

rows = db._conn.execute("SELECT question_id, response FROM responses").fetchall()
print("DB test OK:", rows)
db.close()