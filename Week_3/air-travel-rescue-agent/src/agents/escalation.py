import logging

from src.models.schemas import (
    EscalationOutput,
    EscalationReason,
    Severity,
)


logger = logging.getLogger(__name__)

def escalation_agent(state, escalation_chain):
    payload = {
        "issue_description": state.get("issue_description"),
        "disruption_type": state.get("disruption_type"),
        "severity": state.get("severity"),
        "origin": state.get("origin"),
        "destination": state.get("destination"),
        "original_flight": state.get("original_flight"),
        "last_error": state.get("last_error"),
        "retry_count": state.get("retry_count", 0),
        "ranked_options": state.get("ranked_options", []),
        "action_history": state.get("action_history", []),
    }

    try:
        result: EscalationOutput = escalation_chain.invoke(payload)
    except Exception:
        logger.exception("Escalation model failed; using deterministic fallback")

        last_error = state.get("last_error")
        no_viable_options = not state.get("ranked_options")

        if last_error:
            reason = EscalationReason.TOOL_FAILURE
            summary = last_error
        elif no_viable_options:
            reason = EscalationReason.NO_VIABLE_FLIGHT
            summary = (
                "No available replacement flight meets both your arrival "
                "deadline and maximum extra-cost limit."
            )
        else:
            reason = EscalationReason.OTHER
            summary = "Automated flight recovery could not be completed."

        result = EscalationOutput(
            escalation_required=True,
            reason=reason,
            priority=state.get("severity") or Severity.HIGH,
            summary=summary,
            actions_attempted=[
                record.action
                for record in state.get("action_history", [])
            ],
            recommended_human_action=(
                "A travel support agent should review alternate dates, nearby "
                "airports, or an exception to the current constraints."
            ),
        )

    return {"escalation_required": True, "escalation_output": result}
