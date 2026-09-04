from src.models.schemas import (
    DisruptionType,
    TriageOutput,
)


def triage_agent(state, triage_chain):

    result: TriageOutput = triage_chain.invoke({
        "origin": state.get("origin"),
        "destination": state.get("destination"),
        "flight_number": state.get("flight_number"),
        "travel_date": state.get("travel_date"),
        "issue_description": state.get("issue_description"),
        "arrival_deadline": state.get("arrival_deadline"),
        "max_extra_cost": state.get("max_extra_cost"),
        "preferences": state.get("preferences", []),
    })

    search_alternatives = result.search_alternatives

    # Deterministic workflow normalization
    if result.disruption_type in {
        DisruptionType.CANCELLED,
        DisruptionType.MISSED_CONNECTION,
    }:
        search_alternatives = True

    return {
        "disruption_type": result.disruption_type,
        "severity": result.severity,
        "recovery_required": result.recovery_required,
        "search_alternatives": search_alternatives,
    }