"""Build the Neo4j property graph from the complete OrgMind corpus."""

import argparse
from collections.abc import Sequence

from llama_index.core import PropertyGraphIndex

from config import NEO4J_DATABASE
from graph.neo4j_client import get_driver
from ingestion.factories import (
    create_embedding_model,
    create_graph_store,
    create_kg_extractor,
)
from ingestion.load_documents import load_documents


def graph_counts() -> tuple[int, int]:
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            record = session.run(
                """
                MATCH (n)
                WHERE NOT n:VectorChunk
                WITH count(n) AS nodes
                OPTIONAL MATCH (a)-[r]->(b)
                WHERE NOT a:VectorChunk AND NOT b:VectorChunk
                RETURN nodes, count(r) AS relationships
                """
            ).single()
            return record["nodes"], record["relationships"]
    finally:
        driver.close()


def reset_property_graph() -> None:
    """Delete property-graph data while preserving the vector index nodes."""
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                "MATCH (n) WHERE NOT n:VectorChunk DETACH DELETE n"
            ).consume()
    finally:
        driver.close()


def build_knowledge_graph(batch_size: int = 5, reset: bool = False) -> dict:
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    documents = load_documents()
    if not documents:
        raise RuntimeError("No source documents were found")

    existing_nodes, _ = graph_counts()
    if existing_nodes and not reset:
        raise RuntimeError(
            f"Neo4j already contains {existing_nodes} property-graph nodes. "
            "Use --reset to rebuild them explicitly."
        )
    if reset:
        print("Resetting existing property-graph data (VectorChunk nodes are preserved)...")
        reset_property_graph()

    embed_model = create_embedding_model()
    graph_store = create_graph_store()
    extractor = create_kg_extractor()
    batches = [
        documents[index : index + batch_size]
        for index in range(0, len(documents), batch_size)
    ]

    for number, batch in enumerate(batches, start=1):
        print(f"Processing graph batch {number}/{len(batches)} ({len(batch)} documents)...")
        PropertyGraphIndex.from_documents(
            batch,
            kg_extractors=[extractor],
            embed_model=embed_model,
            property_graph_store=graph_store,
            show_progress=True,
            use_async=False,
        )

    node_count, relationship_count = graph_counts()
    return {
        "documents": len(documents),
        "batches": len(batches),
        "nodes": node_count,
        "relationships": relationship_count,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the OrgMind corpus into a Neo4j property graph."
    )
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and rebuild property-graph data; preserves VectorChunk nodes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and count documents without calling Neo4j, Nebius, or embeddings.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be greater than zero")
    if args.dry_run:
        documents = load_documents()
        batches = (len(documents) + args.batch_size - 1) // args.batch_size
        print(f"Dry run: {len(documents)} documents in {batches} batches")
        return 0

    result = build_knowledge_graph(batch_size=args.batch_size, reset=args.reset)
    print(
        "Knowledge graph complete: "
        f"{result['documents']} documents, {result['nodes']} nodes, "
        f"{result['relationships']} relationships"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
