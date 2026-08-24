
from typing import Any

from graph.neo4j_client import get_driver
from config import NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_URI

import os


DB = os.getenv("NEO4J_DATABASE", "neo4j")


GRAPH_QUERIES = {

 # Q1:
    # What database does Phoenix use for its online feature cache?
    "project_feature_technology": """
        MATCH (decision:DECISION)-[:AFFECTS]->(
            project:PROJECT {name: $project}
        )

        MATCH (decision)-[:INVOLVES]->(
            technology:TECHNOLOGY
        )

        WHERE toLower(decision.name)
              CONTAINS toLower($keyword)

        RETURN
            project.name AS project,
            decision.name AS decision,
            technology.name AS technology
    """,


    # Q2:
    # What is the purpose of Project Atlas?
    #
    # Use the graph to find the Project document,
    # then retrieve its source Chunk.
    "project_purpose": """
        MATCH (doc:DOCUMENT)-[:DESCRIBES]->(
            project:PROJECT {name: $project}
        )

        MATCH (chunk:Chunk)

        WHERE chunk.file_path ENDS WITH doc.path

        RETURN
            project.name AS project,
            doc.name AS document,
            chunk.file_name AS source_file,
            chunk.text AS evidence
    """,


    # Q3:
    # Why did Atlas adopt Kafka?
    #
    # Graph identifies the relevant decision.
    # Chunk provides the narrative rationale.
    "decision_rationale": """
        MATCH (decision:DECISION)-[:AFFECTS]->(
        project:PROJECT {name: $project}
    )

    MATCH (decision)-[:INVOLVES]->(
        technology:TECHNOLOGY {name: $technology}
    )

    MATCH (doc:DOCUMENT)-[:DOCUMENTS]->(decision)

    MATCH (chunk:Chunk)
    WHERE chunk.file_path ENDS WITH doc.path

    RETURN
        project.name AS project,
        decision.name AS decision,
        technology.name AS technology,
        doc.name AS document,
        chunk.file_name AS source_file,
        chunk.text AS evidence
    """,

    # Q4:
    # Who worked on Project Phoenix and also has Kubernetes experience?
    "person_project_skill": """
        MATCH (p:PERSON)-[:WORKED_ON]->(
            project:PROJECT {name: $project}
        ),
        (p)-[:HAS_SKILL]->(
            skill:SKILL {name: $skill}
        )

        RETURN
            p.name AS person,
            project.name AS project,
            skill.name AS skill

        ORDER BY person
    """,


    # Q5:
    # Which people worked on both Atlas and Phoenix?
    "shared_projects": """
        MATCH (p:PERSON)-[:WORKED_ON]->(
            project1:PROJECT {name: $project1}
        ),
        (p)-[:WORKED_ON]->(
            project2:PROJECT {name: $project2}
        )

        RETURN DISTINCT
            p.name AS person,
            project1.name AS project1,
            project2.name AS project2

        ORDER BY person
    """,


    # Q7:
    # Which projects were worked on by Search team members?
    "team_projects": """
        MATCH (p:PERSON)-[:MEMBER_OF]->(
            team:TEAM {name: $team}
        ),
        (p)-[:WORKED_ON]->(
            project:PROJECT
        )

        RETURN DISTINCT
            team.name AS team,
            p.name AS person,
            project.name AS project

        ORDER BY project, person
    """,


    # Q8:
    # Which technologies are used by projects led by Alice?
    "leader_technologies": """
        MATCH (
            leader:PERSON {name: $person}
        )-[:LEADS]->(
            project:PROJECT
        ),
        (project)-[:USES]->(
            technology:TECHNOLOGY
        )

        RETURN
            leader.name AS leader,
            project.name AS project,
            technology.name AS technology

        ORDER BY technology
    """,


    # Q6:
    # Who approved architecture decisions for technologies used by Atlas?
    "decision_approvers": """
        MATCH (
            project:PROJECT {name: $project}
        )-[:USES]->(
            technology:TECHNOLOGY
        )

        MATCH (
            decision:DECISION
        )-[:AFFECTS]->(
            project
        )

        MATCH (
            decision
        )-[:INVOLVES]->(
            technology
        )

        MATCH (
            person:PERSON
        )-[:APPROVED]->(
            decision
        )

        RETURN DISTINCT
            person.name AS approver,
            decision.name AS decision,
            technology.name AS technology,
            project.name AS project

        ORDER BY decision
    """,


    # Q9:
    # Who is the best Kafka expert based on project experience
    # and documented technical decisions?
    "expert_lookup": """
        MATCH (
            person:PERSON
        )-[:HAS_SKILL]->(
            skill:SKILL {name: $technology}
        )

        OPTIONAL MATCH (
            person
        )-[:WORKED_ON]->(
            project:PROJECT
        )-[:USES]->(
            tech:TECHNOLOGY {name: $technology}
        )

        OPTIONAL MATCH (
            person
        )-[:PROPOSED|APPROVED]->(
            decision:DECISION
        )-[:INVOLVES]->(
            decision_tech:TECHNOLOGY {name: $technology}
        )

        WITH
            person,
            collect(DISTINCT project.name) AS projects,
            collect(DISTINCT decision.name) AS decisions

        RETURN
            person.name AS person,
            projects,
            decisions,
            size(projects) AS project_count,
            size(decisions) AS decision_count,
            size(projects) + (2 * size(decisions)) AS expertise_score

        ORDER BY expertise_score DESC, person
    """,


    # Q10:
    # Decisions affecting projects owned by teams whose members
    # also worked on Phoenix.
    "multi_hop_decisions": """
        MATCH (
        member:PERSON
    )-[:WORKED_ON]->(
        reference_project:PROJECT {name: $project}
    )

    MATCH (
        member
    )-[:MEMBER_OF]->(
        team:TEAM
    )

    MATCH (
        affected_project:PROJECT
    )-[:OWNED_BY]->(
        team
    )

    MATCH (
        decision:DECISION
    )-[:AFFECTS]->(
        affected_project
    )

    RETURN
        decision.name AS decision,
        affected_project.name AS project,
        team.name AS team,
        collect(DISTINCT member.name) AS connecting_people

    ORDER BY decision
    """,
}


def run_cypher(
    query: str,
    parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Execute a read-only Cypher query and return results
    as a list of dictionaries.
    """

    driver = get_driver()

    try:
        with driver.session(database=DB) as session:
            result = session.run(
                query,
                parameters or {},
            )

            return [
                dict(record)
                for record in result
            ]

    finally:
        driver.close()


def retrieve_graph(
    intent: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Run one of the supported graph retrieval patterns.
    """

    if intent not in GRAPH_QUERIES:
        raise ValueError(
            f"Unsupported graph intent: {intent}. "
            f"Supported intents: {sorted(GRAPH_QUERIES)}"
        )

    rows = run_cypher(
        GRAPH_QUERIES[intent],
        parameters,
    )

    return {
        "intent": intent,
        "parameters": parameters,
        "result_count": len(rows),
        "results": rows,
    }
