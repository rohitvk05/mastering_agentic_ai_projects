import logging

from src.models.schemas import QAOutput


logger = logging.getLogger(__name__)


def qa_agent(state, qa_chain):

    try:
        result: QAOutput = qa_chain.invoke({
            "issue_description": state.get("issue_description"),
            "disruption_type": state.get("disruption_type"),
            "arrival_deadline": state.get("arrival_deadline"),
            "max_extra_cost": state.get("max_extra_cost"),
            "preferences": state.get("preferences", []),

            "original_flight": state.get("original_flight"),
            "recommended_plan": state.get("recommended_plan"),

            "approval_status": state.get("approval_status"),
            "booking_updated": state.get("booking_updated"),

            "resolution_status": state.get("resolution_status"),
            "resolution_summary": state.get("resolution_summary"),

            "action_history": state.get("action_history", []),
            "escalation_output": state.get("escalation_output"),
        })
    except Exception:
        # QA is observational and must not turn a valid traveler outcome into
        # a failed interaction when its model response is malformed.
        logger.exception("QA model failed; preserving completed workflow result")
        return {"qa_review": None}

    return {
        "qa_review": result
    }
