import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
graph = json.loads((ROOT / "evaluation" / "graph_ground_truth.json").read_text())
questions = json.loads((ROOT / "evaluation" / "questions.json").read_text())

node_ids = {n["id"] for n in graph["nodes"]}
errors = []

for edge in graph["edges"]:
    if edge["source"] not in node_ids:
        errors.append(f"Missing source node: {edge}")
    if edge["target"] not in node_ids:
        errors.append(f"Missing target node: {edge}")

for q in questions:
    for entity in q.get("supporting_entities", []):
        if entity not in node_ids:
            errors.append(f"Question {q['id']} references missing entity: {entity}")

print("Node counts:", dict(Counter(n["label"] for n in graph["nodes"])))
print("Total nodes:", len(graph["nodes"]))
print("Total relationships:", len(graph["edges"]))
print("Evaluation questions:", len(questions))

if errors:
    for e in errors:
        print("ERROR:", e)
    raise SystemExit(1)

print("Validation passed.")
