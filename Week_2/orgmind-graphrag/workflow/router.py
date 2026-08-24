import json
import re
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field, model_validator

from config import NEBIUS_API_KEY, NEBIUS_BASE_URL, NEBIUS_MODEL
from retrieval.graph_retriever import GRAPH_QUERIES
from retrieval.query_planner import (
    KNOWN_CAPABILITIES,
    KNOWN_PEOPLE,
    KNOWN_PROJECTS,
    KNOWN_TEAMS,
    plan_graph_query,
)


GraphIntent = Literal[
    "project_feature_technology",
    "project_purpose",
    "decision_rationale",
    "person_project_skill",
    "shared_projects",
    "decision_approvers",
    "team_projects",
    "leader_technologies",
    "expert_lookup",
    "multi_hop_decisions",
]

GRAPH_INTENT_PARAMS = {
    intent: sorted(set(re.findall(r"\$([A-Za-z_]\w*)", query)))
    for intent, query in GRAPH_QUERIES.items()
}


class RetrievalPlan(BaseModel):
    strategy: Literal["graph", "vector", "hybrid"]
    graph_intent: GraphIntent | None = None
    parameters: dict = Field(default_factory=dict)
    reason: str

    @model_validator(mode="after")
    def validate_graph_plan(self):
        if self.strategy == "vector":
            self.graph_intent = None
            self.parameters = {}
            return self
        if self.graph_intent is None:
            raise ValueError(f"{self.strategy} retrieval requires a graph_intent")
        required = set(GRAPH_INTENT_PARAMS[self.graph_intent])
        missing = required - set(self.parameters)
        if missing:
            raise ValueError(
                f"{self.graph_intent} is missing parameters: {sorted(missing)}"
            )
        return self


class EvidenceGrade(BaseModel):
    sufficient: bool
    missing_information: str = ""
    recommended_strategy: Literal["graph", "vector", "hybrid", "none"]
    reason: str


def _client() -> OpenAI:
    if not NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not configured in .env")
    return OpenAI(api_key=NEBIUS_API_KEY, base_url=NEBIUS_BASE_URL)


def _json_completion(prompt: str, max_tokens: int = 450) -> dict:
    response = _client().chat.completions.create(
        model=NEBIUS_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The model returned an empty JSON response")
    return json.loads(content)


def _deterministic_plan(question: str) -> RetrievalPlan | None:
    """Return a validated plan for graph patterns supported by local Cypher."""
    graph_plan = plan_graph_query(question)
    intent = graph_plan["intent"]
    if intent is None:
        return None

    narrative_terms = ("why", "explain", "rationale", "purpose")
    needs_narrative = any(term in question.lower() for term in narrative_terms)
    strategy = "hybrid" if needs_narrative else "graph"
    return RetrievalPlan(
        strategy=strategy,
        graph_intent=intent,
        parameters=graph_plan["parameters"],
        reason=(
            "The supported graph pattern needs narrative context."
            if needs_narrative
            else "The question matches a supported structured graph pattern."
        ),
    )


def plan_retrieval(question: str) -> RetrievalPlan:
    deterministic = _deterministic_plan(question)
    if deterministic is not None:
        return deterministic

    intent_specs = "\n".join(
        f"- {name}: required parameters={params}"
        for name, params in GRAPH_INTENT_PARAMS.items()
    )
    prompt = f"""
You plan retrieval for an organizational RAG system. Return only JSON.

Use graph for relationships, intersections, ownership, membership, approvals,
participation, expertise, and multi-hop questions. Use vector for narrative
purpose, explanation, rationale, description, or summary. Use hybrid when both
structured relationships and narrative detail are needed.

Graph intents:
{intent_specs}
Known projects: {KNOWN_PROJECTS}
Known people: {KNOWN_PEOPLE}
Known teams: {KNOWN_TEAMS}
Known skills/technologies: {KNOWN_CAPABILITIES}

Never invent entities. Use listed names exactly. Graph/hybrid requires an
intent and every required parameter. Vector has null intent and no parameters.

Question: {question}

Return: {{"strategy":"graph|vector|hybrid","graph_intent":null,
"parameters":{{}},"reason":"one short sentence"}}
"""
    return RetrievalPlan.model_validate(_json_completion(prompt))


def grade_evidence(
    question: str,
    graph_context: str,
    vector_context: str,
) -> EvidenceGrade:
    prompt = f"""
Grade whether the supplied evidence completely and faithfully answers the
question. Do not answer it or use outside knowledge. List questions require
evidence for the complete set; why/purpose questions usually require narrative
evidence; relationship questions may use graph evidence.

Question: {question}
Graph evidence:\n{graph_context}
Vector evidence:\n{vector_context}

Return only JSON: {{"sufficient":true,"missing_information":"",
"recommended_strategy":"none|graph|vector|hybrid","reason":"..."}}
"""
    return EvidenceGrade.model_validate(_json_completion(prompt, max_tokens=400))


def replan_retrieval(
    question: str,
    previous_plan: RetrievalPlan,
    grade: EvidenceGrade,
) -> RetrievalPlan:
    prompt = f"""
Create a better retrieval plan after insufficient evidence. Return only JSON.
Do not repeat the same failed plan. Prefer hybrid when one evidence type was
missing. Use only the graph intents and known entities below.

Question: {question}
Previous plan: {previous_plan.model_dump_json()}
Grade: {grade.model_dump_json()}
Graph intents and parameters: {GRAPH_INTENT_PARAMS}
Known projects: {KNOWN_PROJECTS}
Known people: {KNOWN_PEOPLE}
Known teams: {KNOWN_TEAMS}
Known skills/technologies: {KNOWN_CAPABILITIES}

Return: {{"strategy":"graph|vector|hybrid","graph_intent":null,
"parameters":{{}},"reason":"one short sentence"}}
"""
    try:
        return RetrievalPlan.model_validate(_json_completion(prompt))
    except (KeyError, ValueError):
        deterministic = _deterministic_plan(question)
        if deterministic is None:
            raise
        if deterministic.strategy == "graph":
            deterministic = RetrievalPlan(
                strategy="hybrid",
                graph_intent=deterministic.graph_intent,
                parameters=deterministic.parameters,
                reason="The malformed replan was replaced with a validated hybrid fallback.",
            )
        return deterministic


def route_query(question: str) -> str:
    """Compatibility helper for callers that only need the chosen route."""
    return plan_retrieval(question).strategy
