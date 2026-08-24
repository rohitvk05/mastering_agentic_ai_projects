from typing import Any

from retrieval.graph_retriever import retrieve_graph
from retrieval.vector_retriever import retrieve_vector


def retrieve_hybrid(
    question: str,
    intent: str,
    parameters: dict[str, Any],
    top_k: int = 5,
) -> dict[str, Any]:
    """Retrieve structured graph rows and narrative vector evidence."""
    graph_response = retrieve_graph(intent, parameters)
    vector_response = retrieve_vector(question, top_k=top_k)
    return {
        "question": question,
        "strategy": "hybrid",
        "graph_results": graph_response["results"],
        "vector_results": vector_response["results"],
    }
