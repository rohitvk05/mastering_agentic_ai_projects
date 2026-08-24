from typing import Any, Literal, TypedDict


class RAGState(TypedDict, total=False):
    question: str
    plan: dict[str, Any]
    route: Literal["graph", "vector", "hybrid"]
    graph_results: list[dict[str, Any]]
    vector_results: list[dict[str, Any]]
    grade: dict[str, Any]
    attempts: int
    replanned: bool
    route_history: list[dict[str, Any]]
    grader_history: list[dict[str, Any]]
    answer: str
