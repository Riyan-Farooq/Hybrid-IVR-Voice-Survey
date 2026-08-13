import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import tts

print("Installed voices:")
for name in tts.list_voices():
    print(f"  - {name}")
print(f"Voice hint: {config.TTS_VOICE_HINT!r}\n")

text = "How satisfied are you with our service? Press 1 for Very Satisfied."

started = time.perf_counter()
path = tts.synthesize(text)
first = time.perf_counter() - started

started = time.perf_counter()
tts.synthesize(text)
second = time.perf_counter() - started

print(f"File     : {path}")
print(f"FS path  : {tts.fs_path(path)}")
print(f"Size     : {path.stat().st_size} bytes")
print(f"Duration : {tts.duration_seconds(path):.2f}s")
print(f"Generate : {first:.2f}s")
print(f"Cached   : {second:.4f}s")

if second > first / 2:
    print("WARNING: cache does not appear to be working")
else:
    print("Cache OK")