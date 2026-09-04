from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from src.graph.state import TravelState
from src.models.schemas import ApprovalStatus, ResolutionStatus
from src.agents.intake import intake_agent
from src.agents.triage import triage_agent
from src.agents.recovery import recovery_agent
from src.agents.planner import planner_agent
from src.agents.escalation import escalation_agent
from src.agents.qa import qa_agent
from src.graph.nodes import (
    flight_recovery_node, retry_handler_node, create_pending_action_node,
    validate_booking_node, execute_rebooking_node, resolution_check_node,
    handle_rejection_node
)
from src.graph.routing import (
    route_after_intake, route_after_triage, route_after_recovery,
    route_after_planner, route_after_booking_validation,
    route_after_approval, route_after_execution, route_after_rejection
)

import re

def parse_approval_response(response):
    text = str(response).strip().lower()

    normalized = re.sub(r"[^\w\s']", " ", text)
    normalized = " ".join(normalized.split())

    # Check rejection FIRST.
    reject_patterns = [
        r"\bno\b",
        r"\bnope\b",
        r"\bnah\b",
        r"\bno thanks\b",

        r"\bnot that one\b",
        r"\bnot this one\b",
        r"\bi don't want that\b",
        r"\bi dont want that\b",

        r"\bshow me another\b",
        r"\banother option\b",
        r"\banother flight\b",
        r"\bdifferent option\b",
        r"\bdifferent flight\b",
        r"\bsomething else\b",

        r"\breject\b",
        r"\bcancel\b",
        r"\bstop\b",

        r"\bdon'?t\s+(?:want\s+to\s+)?book\b",
        r"\bdo not\s+(?:want\s+to\s+)?book\b",
        r"\bdont\s+(?:want\s+to\s+)?book\b",
    ]

    for pattern in reject_patterns:
        if re.search(pattern, normalized):
            return ApprovalStatus.REJECTED

    approve_patterns = [
        r"\byes\b",
        r"\byeah\b",
        r"\byep\b",
        r"\bsure\b",
        r"\bapprove\b",
        r"\bapproved\b",
        r"\bgo ahead\b",
        r"\bbook it\b",
        r"\bplease book\b",
        r"\bproceed\b",
        r"\bdo it\b",
    ]

    for pattern in approve_patterns:
        if re.search(pattern, normalized):
            return ApprovalStatus.APPROVED

    return ApprovalStatus.PENDING

def build_graph(intake_chain, triage_chain, planner_chain, escalation_chain, qa_chain):
    def intake_node(state):
        return intake_agent(state, intake_chain)

    def triage_node(state):
        return triage_agent(state, triage_chain)

    def planner_node(state):
        return planner_agent(state, planner_chain)

    def missing_information_node(state):
        missing = state.get("missing_information", [])
        labels = {
            "origin": "departure airport",
            "destination": "destination airport",
            "flight_number": "flight number",
            "travel_date": "travel date",
            "booking_id": "booking ID",
            "arrival_deadline": "desired arrival time",
            "max_extra_cost": "maximum extra cost",
            "preferences": "flight preferences",
        }
        readable = [labels.get(field, field.replace("_", " ")) for field in missing]

        if len(readable) > 1:
            details = ", ".join(readable[:-1]) + f", and {readable[-1]}"
        elif readable:
            details = readable[0]
        else:
            details = "trip details"

        return {
            "resolution_summary": f"Please tell me your {details}."
        }

    def await_approval_node(state):
        action = state["pending_action"]

        response = interrupt({
        "type": "approval_required",
        "message": (
            f"Rebook onto {action.flight_number} "
            f"for an additional ${action.additional_cost:.2f}?"
        ),
        "flight_number": action.flight_number,
        "additional_cost": action.additional_cost,
    })

        status = parse_approval_response(response)

        print("HITL RESPONSE:", response)
        print("PARSED STATUS:", status)

        return {
        "approval_status": status
    }

    def escalation_agent_node(state):
        result = escalation_agent(state, escalation_chain)
        return {**result, "resolution_status": ResolutionStatus.ESCALATED}

    def qa_node(state):
        return qa_agent(state, qa_chain)

    builder = StateGraph(TravelState)
    builder.add_node("intake", intake_node)
    builder.add_node("missing_information", missing_information_node)
    builder.add_node("triage", triage_node)
    builder.add_node("flight_recovery", flight_recovery_node)
    builder.add_node("retry", retry_handler_node)
    builder.add_node("recovery_agent", recovery_agent)
    builder.add_node("planner", planner_node)
    builder.add_node("create_pending_action", create_pending_action_node)
    builder.add_node("validate_booking", validate_booking_node)
    builder.add_node("await_approval", await_approval_node)
    builder.add_node("execute_rebooking", execute_rebooking_node)
    builder.add_node("resolution_check", resolution_check_node)
    builder.add_node("escalate", escalation_agent_node)
    builder.add_node("qa", qa_node)
    builder.add_node(
    "handle_rejection",
    handle_rejection_node,
)

    builder.add_edge(START, "intake")
    builder.add_conditional_edges("intake", route_after_intake, {
        "missing_information": "missing_information", "triage": "triage"
    })
    builder.add_edge("missing_information", END)

    builder.add_conditional_edges("triage", route_after_triage, {
        "flight_recovery": "flight_recovery", "escalate": "escalate"
    })
    builder.add_conditional_edges("flight_recovery", route_after_recovery, {
        "recovery_agent": "recovery_agent", "retry": "retry", "escalate": "escalate"
    })
    builder.add_edge("retry", "flight_recovery")
    builder.add_edge("recovery_agent", "planner")

    builder.add_conditional_edges("planner", route_after_planner, {
        "create_pending_action": "create_pending_action", "escalate": "escalate"
    })
    builder.add_edge("create_pending_action", "validate_booking")
    builder.add_conditional_edges("validate_booking", route_after_booking_validation, {
        "await_approval": "await_approval", "escalate": "escalate"
    })
    builder.add_conditional_edges(
    "await_approval",
    route_after_approval,
    {
        "execute_rebooking": "execute_rebooking",
        "handle_rejection": "handle_rejection",
        "await_approval": "await_approval",
    },)
    builder.add_conditional_edges("execute_rebooking", route_after_execution, {
        "resolution_check": "resolution_check", "escalate": "escalate"
    })
    builder.add_conditional_edges(
    "handle_rejection",
    route_after_rejection,
    {
        "planner": "planner",
        "escalate": "escalate",
    },)
    builder.add_edge("resolution_check", "qa")
    builder.add_edge("escalate", "qa")
    builder.add_edge("qa", END)

    return builder.compile(checkpointer=MemorySaver())
