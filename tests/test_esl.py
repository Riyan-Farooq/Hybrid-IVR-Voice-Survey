import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from esl_client import ESLClient

esl = ESLClient(config.FS_HOST, config.FS_PORT, config.FS_PASSWORD)
esl.connect()
print("ESL connected")

uuid = None
try:
    uuid = esl.originate(config.TARGET_EXTENSION)

    digit = esl.ask_question(
        uuid=uuid,
        prompt="tone_stream://%(500,0,640)",
        var_name="test_digit",
        valid_digits="1234",
    )
    print(f"You pressed: {digit!r}")
    print("Test passed!")
finally:
    if uuid:
        esl.hangup(uuid)
    esl.close()