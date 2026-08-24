import json
from pathlib import Path

QUESTIONS_FILE = Path(__file__).with_name("questions.json")

def load_questions():
    return json.loads(QUESTIONS_FILE.read_text())

if __name__ == "__main__":
    for q in load_questions():
        print(f"[{q['category']}] {q['question']}")
