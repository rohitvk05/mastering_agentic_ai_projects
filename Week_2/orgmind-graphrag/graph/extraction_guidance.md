# Knowledge Graph Extraction Rules

1. Normalize extracted facts to the canonical schema in `graph/schema.py`.
2. Create a `Person` only for a named employee.
3. Keep `Skill` and `Technology` as separate node types.
4. Use `WORKED_ON`, `HAS_SKILL`, `LEADS`, `PROPOSED`, and `APPROVED` only when explicitly stated.
5. Connect each `Decision` to its affected `Project` and involved `Technology`.
6. Preserve source document IDs for later evidence/citations.
7. Do not infer unstated skills, ownership, approvals, or project participation.
