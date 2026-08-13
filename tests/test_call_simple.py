import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from esl_client import ESLClient

esl = ESLClient(config.FS_HOST, config.FS_PORT, config.FS_PASSWORD)
esl.connect()
print("ESL connected")

# Simplest possible call — no park
resp = esl.api(f"originate user/{config.TARGET_EXTENSION} &echo()")
print("Response:")
print(resp)

esl.close()