import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.chaster_actions import parse_chaster_intent

print(parse_chaster_intent("what can we do with his lock?"))
