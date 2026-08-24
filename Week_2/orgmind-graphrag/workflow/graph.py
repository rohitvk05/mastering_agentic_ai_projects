from openai import OpenAI
from langgraph.graph import END, START, StateGraph

from config import NEBIUS_API_KEY, NEBIUS_BASE_URL, NEBIUS_MODEL
from retrieval.graph_retriever import retrieve_graph
from retrieval.vector_retriever import retrieve_vector
from workflow.router import (
    EvidenceGrade,
    RetrievalPlan,
    grade_evidence,
    plan_retrieval,
    replan_retrieval,
)
from workflow.state import RAGState


MAX_RETRIEVAL_ATTEMPTS = 2

ANSWER_SYSTEM_PROMPT = """
You answer questions about the fictional Acme AI organization using only the
retrieved evidence. Graph rows are authoritative for relationships, sets,
membership, ownership, projects, technologies, people, decisions, and multi-hop
results. Vector passages supply narrative explanations, rationale, purpose, and
context. Include every distinct matching graph result for list questions. Never
invent or infer unsupported relationships. If evidence is insufficient, say so.
Be concise but complete.
"""


def format_graph_evidence(results: list[dict]) -> str:
    if not results:
        return "No graph evidence retrieved."
    return "\n".join(
        f"Graph evidence {index}: "
        + " | ".join(
            f"{key}: {value}" for key, value in row.items() if value is not None
        )
        for index, row in enumerate(results, start=1)
    )


def format_vector_evidence(results: list[dict]) -> str:
    if not results:
        return "No vector evidence retrieved."
    blocks = []
    for item in results:
        score = item.get("score")
        score_text = f"{score:.4f}" if score is not None else "n/a"
        blocks.append(
            f"Source: {item.get('file_name', 'unknown')}\n"
            f"Similarity: {score_text}\n\n{item.get('text', '')}"
        )
    return "\n\n---\n\n".join(blocks)


def execute_plan(question: str, plan: RetrievalPlan) -> dict:
    graph_results: list[dict] = []
    vector_results: list[dict] = []
    if plan.strategy in {"graph", "hybrid"}:
        graph_results = retrieve_graph(
            plan.graph_intent,
            plan.parameters,
        )["results"]
    if plan.strategy in {"vector", "hybrid"}:
        vector_results = retrieve_vector(question, top_k=5)["results"]
    return {
        "graph_results": graph_results,
        "vector_results": vector_results,
    }


def generate_answer(
    question: str,
    graph_results: list[dict],
    vector_results: list[dict],
) -> str:
    if not NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not configured in .env")
    graph_context = format_graph_evidence(graph_results)
    vector_context = format_vector_evidence(vector_results)
    prompt = f"""
Question: {question}

Graph evidence ({len(graph_results)} rows):
{graph_context}

Vector evidence ({len(vector_results)} passages):
{vector_context}

Answer using only this evidence. Include all unique matching graph rows.
"""
    client = OpenAI(api_key=NEBIUS_API_KEY, base_url=NEBIUS_BASE_URL)
    response = client.chat.completions.create(
        model=NEBIUS_MODEL,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=500,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The answer model returned no content")
    return content.strip()


def planner_node(state: RAGState) -> dict:
    plan = plan_retrieval(state["question"])
    plan_data = plan.model_dump()
    return {
        "plan": plan_data,
        "route": plan.strategy,
        "attempts": 1,
        "replanned": False,
        "route_history": [{"attempt": 1, **plan_data}],
        "grader_history": [],
    }


def retrieval_node(state: RAGState) -> dict:
    return execute_plan(
        state["question"],
        RetrievalPlan.model_validate(state["plan"]),
    )


def grader_node(state: RAGState) -> dict:
    grade = grade_evidence(
        state["question"],
        format_graph_evidence(state.get("graph_results", [])),
        format_vector_evidence(state.get("vector_results", [])),
    )
    history = list(state.get("grader_history", []))
    history.append({"attempt": state.get("attempts", 1), **grade.model_dump()})
    return {"grade": grade.model_dump(), "grader_history": history}


def after_grading(state: RAGState) -> str:
    grade = EvidenceGrade.model_validate(state["grade"])
    if grade.sufficient or state.get("attempts", 1) >= MAX_RETRIEVAL_ATTEMPTS:
        return "answer"
    return "replan"


def replanner_node(state: RAGState) -> dict:
    previous = RetrievalPlan.model_validate(state["plan"])
    grade = EvidenceGrade.model_validate(state["grade"])
    graph_empty = not state.get("graph_results")

    if previous.strategy == "graph" and graph_empty:
        new_plan = RetrievalPlan(
            strategy="hybrid",
            graph_intent=previous.graph_intent,
            parameters=previous.parameters,
            reason="Graph retrieval was empty, so vector evidence was added.",
        )
    else:
        new_plan = replan_retrieval(state["question"], previous, grade)

    same_plan = (
        new_plan.strategy == previous.strategy
        and new_plan.graph_intent == previous.graph_intent
        and new_plan.parameters == previous.parameters
    )
    if same_plan and previous.strategy == "graph":
        new_plan = RetrievalPlan(
            strategy="hybrid",
            graph_intent=previous.graph_intent,
            parameters=previous.parameters,
            reason="The graph evidence was insufficient, so vector evidence was added.",
        )

    attempt = state.get("attempts", 1) + 1
    plan_data = new_plan.model_dump()
    history = list(state.get("route_history", []))
    history.append({"attempt": attempt, **plan_data})
    return {
        "plan": plan_data,
        "route": new_plan.strategy,
        "attempts": attempt,
        "replanned": True,
        "route_history": history,
    }


def answer_node(state: RAGState) -> dict:
    return {
        "answer": generate_answer(
            state["question"],
            state.get("graph_results", []),
            state.get("vector_results", []),
        )
    }


def build_workflow():
    workflow = StateGraph(RAGState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("grader", grader_node)
    workflow.add_node("replan", replanner_node)
    workflow.add_node("answer", answer_node)
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "retrieve")
    workflow.add_edge("retrieve", "grader")
    workflow.add_conditional_edges(
        "grader",
        after_grading,
        {"answer": "answer", "replan": "replan"},
    )
    workflow.add_edge("replan", "retrieve")
    workflow.add_edge("answer", END)
    return workflow.compile()
