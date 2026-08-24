
"""
Reusable Vector RAG retriever for OrgMind.

This module connects to the EXISTING Neo4j vector index.
It does not ingest documents or rebuild embeddings.
"""

from functools import lru_cache
from typing import Any
import os

from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.neo4jvector import Neo4jVectorStore

from config import (
    NEO4J_URI,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
)


DB = os.getenv(
    "NEO4J_DATABASE",
    "neo4j",
)

VECTOR_INDEX_NAME = "orgmind_vector_index"
VECTOR_NODE_LABEL = "VectorChunk"

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def get_embed_model():
    """
    Load the local embedding model once per Python process.
    """

    return HuggingFaceEmbedding(
        model_name=EMBED_MODEL_NAME
    )


@lru_cache(maxsize=1)
def get_vector_index():
    """
    Connect LlamaIndex to the existing Neo4j vector index.

    No document ingestion happens here.
    """

    embed_model = get_embed_model()

    # Determine the embedding dimension from the model.
    embedding_dimension = len(
        embed_model.get_text_embedding(
            "embedding dimension probe"
        )
    )

    vector_store = Neo4jVectorStore(
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        url=NEO4J_URI,

        database=DB,

        index_name=VECTOR_INDEX_NAME,
        node_label=VECTOR_NODE_LABEL,

        embedding_dimension=embedding_dimension,

        embedding_node_property="embedding",
        text_node_property="text",
    )

    return VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=embed_model,
    )


def retrieve_vector(
    question: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """
    Retrieve the top-k semantically similar document chunks.

    Returns structured retrieval evidence without
    generating an LLM answer.
    """

    if top_k < 1:
        raise ValueError(
            "top_k must be greater than 0"
        )

    index = get_vector_index()

    retriever = index.as_retriever(
        similarity_top_k=top_k
    )

    retrieved_nodes = retriever.retrieve(
        question
    )

    results = []

    for rank, item in enumerate(
        retrieved_nodes,
        start=1,
    ):
        results.append({
            "rank": rank,
            "score": (
                float(item.score)
                if item.score is not None
                else None
            ),
            "file_name":
                item.node.metadata.get(
                    "file_name"
                ),
            "file_path":
                item.node.metadata.get(
                    "file_path"
                ),
            "doc_id":
                item.node.metadata.get(
                    "doc_id"
                ),
            "doc_type":
                item.node.metadata.get(
                    "doc_type"
                ),
            "text":
                item.node.text,
        })

    return {
        "question": question,
        "top_k": top_k,
        "result_count": len(results),
        "results": results,
    }
