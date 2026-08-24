# OrgMind Agentic RAG

An agentic organizational-knowledge RAG system using a fictional company called
**Acme AI**. The application plans and grades retrieval across Graph, Vector,
and Hybrid routes, and can replan once when its first evidence is insufficient.

## Architecture

The same Markdown corpus powers two Neo4j indexes:

```text
data/
  ├── python -m ingestion.build_knowledge_graph → property graph
  └── python -m ingestion.build_vector_index    → vector index
                                                       ↓
                                            Agentic RAG workflow
                                      (Graph / Vector / Hybrid route)
                                                       ↓
                                               Streamlit application
```

## Corpus

- 10 people profiles
- 4 project overviews
- 8 architecture decision records
- 6 meeting-note documents
- 5 cross-cutting technical documents

## Important files

- `graph/schema.py` — canonical node/relationship contract
- `graph/schema.md` — human-readable schema
- `graph/schema.cypher` — Neo4j constraints/indexes
- `ingestion/factories.py` — shared LLM, embedding, and Neo4j factories
- `ingestion/build_knowledge_graph.py` — reproducible property-graph builder
- `ingestion/build_vector_index.py` — reproducible vector-index builder
- `workflow/graph.py` — planner, retrieval, grading, replanning, and answering
- `ui/app.py` — Streamlit application
- `data/dataset_manifest.json` — canonical dataset metadata
- `evaluation/graph_ground_truth.json` — evaluation-only graph truth
- `evaluation/questions.json` — 10 questions with expected answers
- `evaluation/validate_dataset.py` — consistency checker

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Configure `NEBIUS_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, and
`NEO4J_PASSWORD` in `.env`.

## Validate the corpus

```bash
.venv/bin/python evaluation/validate_dataset.py
```

## Build the indexes

Inspect what each command will process without contacting external services:

```bash
.venv/bin/python -m ingestion.build_knowledge_graph --dry-run
.venv/bin/python -m ingestion.build_vector_index --dry-run
```

Build into an empty Neo4j database:

```bash
.venv/bin/python -m ingestion.build_knowledge_graph
.venv/bin/python -m ingestion.build_vector_index
```

Both builders refuse to overwrite existing data. Rebuild explicitly when
needed:

```bash
# Deletes property-graph nodes but preserves VectorChunk nodes.
.venv/bin/python -m ingestion.build_knowledge_graph --reset

# Deletes VectorChunk nodes but preserves the property graph.
.venv/bin/python -m ingestion.build_vector_index --rebuild
```

Knowledge-graph extraction uses the Nebius model and may incur API usage.

## Run the application

```bash
.venv/bin/python -m streamlit run ui/app.py
```

The UI shows the question, chosen route, whether replanning occurred, the final
grounded answer, and expandable evidence/debug details.

## Notebooks

The five notebooks document the development and evaluation process. The Python
modules provide the reproducible operational path; users do not need to execute
the notebooks to build or run the application.
