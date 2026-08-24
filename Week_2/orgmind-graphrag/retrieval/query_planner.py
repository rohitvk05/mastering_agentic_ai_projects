
import json
from pathlib import Path

from config import ROOT_DIR


# ---------------------------------------------------------
# Load known organizational entities
# ---------------------------------------------------------

MANIFEST_PATH = ROOT_DIR / "data" / "dataset_manifest.json"

_manifest = json.loads(
    MANIFEST_PATH.read_text()
)

KNOWN_PROJECTS = [
    item["name"]
    for item in _manifest["projects"]
]

KNOWN_PEOPLE = [
    item["name"]
    for item in _manifest["people"]
]

KNOWN_TEAMS = [
    item["name"]
    for item in _manifest["teams"]
]

KNOWN_SKILLS = [
    item["name"]
    for item in _manifest["skills"]
]

KNOWN_TECHNOLOGIES = [
    item["name"]
    for item in _manifest["technologies"]
]

# A query might refer to Kafka as either a skill or technology.
KNOWN_CAPABILITIES = sorted(
    set(KNOWN_SKILLS + KNOWN_TECHNOLOGIES)
)


def _find_all(text: str, candidates: list[str]) -> list[str]:
    """
    Return all candidate entity names explicitly mentioned
    in the question.
    """

    text_lower = text.lower()

    return [
        candidate
        for candidate in candidates
        if candidate.lower() in text_lower
    ]


def plan_graph_query(question: str) -> dict:
    """
    Convert supported natural-language questions into
    a graph intent and parameter dictionary.

    No LLM is used here.
    """

    q = question.lower()

    projects = _find_all(
        question,
        KNOWN_PROJECTS,
    )

    people = _find_all(
        question,
        KNOWN_PEOPLE,
    )

    teams = _find_all(
        question,
        KNOWN_TEAMS,
    )

    capabilities = _find_all(
        question,
        KNOWN_CAPABILITIES,
    )

    # -----------------------------------------------------
    # Q10 — Multi-hop decisions
    # Put before simpler "decision" rules.
    # -----------------------------------------------------

    if (
        "decision" in q
        and "owned" in q
        and "team" in q
        and len(projects) >= 1
    ):
        return {
            "intent": "multi_hop_decisions",
            "parameters": {
                "project": projects[0],
            },
        }

    # -----------------------------------------------------
    # Q4 — person + project + skill
    # -----------------------------------------------------

    if (
        len(projects) >= 1
        and len(capabilities) >= 1
        and "worked" in q
        and (
            "experience" in q
            or "skill" in q
            or "knows" in q
        )
    ):
        return {
            "intent": "person_project_skill",
            "parameters": {
                "project": projects[0],
                "skill": capabilities[0],
            },
        }

    # -----------------------------------------------------
    # Q5 — people who worked on two projects
    # -----------------------------------------------------

    if (
        len(projects) >= 2
        and "worked" in q
    ):
        return {
            "intent": "shared_projects",
            "parameters": {
                "project1": projects[0],
                "project2": projects[1],
            },
        }

    # -----------------------------------------------------
    # Q6 — decision approvers
    # -----------------------------------------------------

    if (
        "approv" in q
        and "decision" in q
        and len(projects) >= 1
    ):
        return {
            "intent": "decision_approvers",
            "parameters": {
                "project": projects[0],
            },
        }

    # -----------------------------------------------------
    # Q7 — projects connected to a team
    # -----------------------------------------------------

    if (
        len(teams) >= 1
        and "project" in q
        and (
            "member" in q
            or "team" in q
        )
    ):
        return {
            "intent": "team_projects",
            "parameters": {
                "team": teams[0],
            },
        }

    # -----------------------------------------------------
    # Q8 — technologies used by projects led by a person
    # -----------------------------------------------------

    if (
        len(people) >= 1
        and "technolog" in q
        and (
            "led by" in q
            or "leads" in q
        )
    ):
        return {
            "intent": "leader_technologies",
            "parameters": {
                "person": people[0],
            },
        }

    # -----------------------------------------------------
    # Q9 — expertise lookup
    # -----------------------------------------------------

    if (
        len(capabilities) >= 1
        and (
            "best person" in q
            or "consult" in q
            or "expert" in q
        )
    ):
        return {
            "intent": "expert_lookup",
            "parameters": {
                "technology": capabilities[0],
            },
        }

    # -----------------------------------------------------
    # Unsupported graph question
    # -----------------------------------------------------

    return {
        "intent": None,
        "parameters": {},
    }
