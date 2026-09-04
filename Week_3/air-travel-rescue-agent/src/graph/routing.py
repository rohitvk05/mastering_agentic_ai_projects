from src.models.schemas import ApprovalStatus
from src.models.schemas import DisruptionType


def route_after_intake(state):
    return "missing_information" if state.get("missing_information") else "triage"

def route_after_triage(state):

    disruption_type = state.get("disruption_type")

    # Unsupported requests should leave the automated recovery flow
    if disruption_type == DisruptionType.UNSUPPORTED:
        return "escalate"

    # Any supported disruption that requires recovery
    # should enter the flight recovery workflow.
    if state.get("recovery_required"):
        return "flight_recovery"

    return "escalate"

def route_after_recovery(state):
    tool_result = state.get("last_tool_result")
    if tool_result and not tool_result.success:
        if tool_result.retryable and state.get("retry_count", 0) < 2:
            return "retry"
        return "escalate"
    if not state.get("ranked_options"):
        return "escalate"
    return "recovery_agent"

def route_after_planner(state):
    return "create_pending_action" if state.get("recommended_plan") else "escalate"

def route_after_booking_validation(state):
    return "escalate" if state.get("last_error") else "await_approval"

def route_after_approval(state):
    status = state.get("approval_status")

    if status == ApprovalStatus.APPROVED:
        return "execute_rebooking"

    if status == ApprovalStatus.REJECTED:
        return "handle_rejection"

    return "await_approval"

def route_after_rejection(state):
    if state.get("ranked_options"):
        return "planner"

    return "escalate"

def route_after_execution(state):
    return "resolution_check" if state.get("booking_updated") else "escalate"
