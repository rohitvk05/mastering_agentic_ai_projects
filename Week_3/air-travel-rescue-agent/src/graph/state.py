from typing import Annotated, Optional
from operator import add
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage

from src.models.schemas import (
    ActionRecord, ApprovalStatus, DisruptionType, EscalationOutput,
    PendingAction, QAOutput, RecoveryOutput, RecoveryPlan,
    ResolutionStatus, Severity, ToolResult
)

class TravelState(TypedDict, total=False):
    session_id: str
    messages: Annotated[list[BaseMessage], add]

    traveler_id: Optional[str]
    booking_id: Optional[str]

    origin: Optional[str]
    destination: Optional[str]
    flight_number: Optional[str]
    travel_date: Optional[str]
    issue_description: Optional[str]
    arrival_deadline: Optional[str]
    max_extra_cost: Optional[float]
    preferences: list[str]
    missing_information: list[str]

    disruption_type: Optional[DisruptionType]
    severity: Optional[Severity]
    recovery_required: bool
    search_alternatives: bool

    original_flight: Optional[dict]

    alternative_flights: list[dict]
    nearby_airports: list[str]
    evaluated_options: list[dict]
    ranked_options: list[dict]
    recovery_output: Optional[RecoveryOutput]

    planner_output: Optional[object]
    recommended_plan: Optional[RecoveryPlan]

    pending_action: Optional[PendingAction]
    approval_status: ApprovalStatus

    action_history: Annotated[list[ActionRecord], add]
    booking_updated: bool

    simulate_search_failure: bool
    simulate_persistent_search_failure: bool

    retry_count: int
    last_error: Optional[str]
    last_tool_result: Optional[ToolResult]

    escalation_required: bool
    escalation_output: Optional[EscalationOutput]

    resolution_status: ResolutionStatus
    resolution_summary: Optional[str]

    qa_review: Optional[QAOutput]

    rejected_flights: list[str]
    rejection_count: int
