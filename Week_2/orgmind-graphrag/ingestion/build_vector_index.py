"""Build the Neo4j vector index from the complete OrgMind corpus."""

import argparse
from collections.abc import Sequence

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter

from config import NEO4J_DATABASE
from graph.neo4j_client import get_driver
from ingestion.factories import (
    VECTOR_INDEX_NAME,
    VECTOR_NODE_LABEL,
    create_embedding_model,
    create_vector_store,
)
from ingestion.load_documents import load_documents


def vector_node_count() -> int:
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            return session.run(
                f"MATCH (n:{VECTOR_NODE_LABEL}) RETURN count(n) AS count"
            ).single()["count"]
    finally:
        driver.close()


def reset_vector_nodes() -> None:
    """Delete vector chunks without touching the property graph."""
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                f"MATCH (n:{VECTOR_NODE_LABEL}) DETACH DELETE n"
            ).consume()
    finally:
        driver.close()


def vector_index_status() -> list[dict]:
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            rows = session.run(
                """
                SHOW VECTOR INDEXES
                YIELD name, state, populationPercent, labelsOrTypes, properties
                WHERE name = $index_name
                RETURN name, state, populationPercent, labelsOrTypes, properties
                """,
                index_name=VECTOR_INDEX_NAME,
            )
            return [dict(row) for row in rows]
    finally:
        driver.close()


def prepare_nodes(chunk_size: int = 256, chunk_overlap: int = 40):
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and less than chunk_size")
    documents = load_documents()
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return documents, splitter.get_nodes_from_documents(documents)


def build_vector_index(
    rebuild: bool = False,
    chunk_size: int = 256,
    chunk_overlap: int = 40,
) -> dict:
    existing = vector_node_count()
    if existing and not rebuild:
        raise RuntimeError(
            f"Neo4j already contains {existing} {VECTOR_NODE_LABEL} nodes. "
            "Use --rebuild to replace them explicitly."
        )
    if rebuild:
        print("Removing existing vector chunks (property-graph data is preserved)...")
        reset_vector_nodes()

    documents, nodes = prepare_nodes(chunk_size, chunk_overlap)
    if not documents:
        raise RuntimeError("No source documents were found")

    embed_model = create_embedding_model()
    embedding_dimension = len(
        embed_model.get_text_embedding("embedding dimension probe")
    )
    vector_store = create_vector_store(embedding_dimension)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )

    return {
        "documents": len(documents),
        "chunks": vector_node_count(),
        "embedding_dimension": embedding_dimension,
        "index": vector_index_status(),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the OrgMind Neo4j vector index."
    )
    parser.add_argument("--chunk-size", type=int, default=256)
    parser.add_argument("--chunk-overlap", type=int, default=40)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and rebuild VectorChunk nodes; preserves the property graph.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and split documents without embeddings or Neo4j calls.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        documents, nodes = prepare_nodes(args.chunk_size, args.chunk_overlap)
        print(f"Dry run: {len(documents)} documents -> {len(nodes)} vector chunks")
        return 0

    result = build_vector_index(
        rebuild=args.rebuild,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(
        "Vector index complete: "
        f"{result['documents']} documents, {result['chunks']} chunks, "
        f"{result['embedding_dimension']} dimensions"
    )
    if result["index"]:
        print(f"Index status: {result['index'][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
