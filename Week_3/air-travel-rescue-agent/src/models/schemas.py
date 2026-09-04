from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

#Why enums?

#Because we don't want this happening:
#"cancel"
#"cancelled"
#"flight cancelled"
#"CANCELLATION"
#"canceled"
#All of the above should become:
    #DisruptionType.CANCELLED
#That makes routing deterministic.

class DisruptionType(str, Enum):
    CANCELLED = "cancelled"
    DELAYED = "delayed"
    MISSED_CONNECTION = "missed_connection"
    SCHEDULE_CHANGE = "schedule_change"
    UNSUPPORTED = "unsupported"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ResolutionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    FAILED = "failed"


class ActionType(str, Enum):
    REBOOK_FLIGHT = "rebook_flight"
    CREATE_SUPPORT_CASE = "create_support_case"


class EscalationReason(str, Enum):
    NO_VIABLE_FLIGHT = "no_viable_flight"
    TOOL_FAILURE = "tool_failure"
    UNSUPPORTED_REQUEST = "unsupported_request"
    POLICY_RESTRICTION = "policy_restriction"
    USER_REQUESTED_HUMAN = "user_requested_human"
    OTHER = "other"


class IntakeOutput(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    flight_number: Optional[str] = None
    travel_date: Optional[str] = None
    booking_id: Optional[str] = None
    issue_description: str
    arrival_deadline: Optional[str] = None
    max_extra_cost: Optional[float] = None
    preferences: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class TriageOutput(BaseModel):
    disruption_type: DisruptionType
    severity: Severity
    recovery_required: bool
    search_alternatives: bool
    urgency_reason: str
    unsupported_reason: Optional[str] = None


class FlightOption(BaseModel):
    flight_number: str
    airline: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    stops: int
    available_seats: int
    fare_difference: float
    connection_airports: list[str] = Field(default_factory=list)


class EvaluatedFlight(BaseModel):
    flight: FlightOption
    meets_deadline: bool
    within_budget: bool
    feasible: bool
    rejection_reasons: list[str] = Field(default_factory=list)


class RecoveryOutput(BaseModel):
    evaluated_options: list[EvaluatedFlight]
    viable_option_count: int
    recovery_possible: bool
    notes: list[str] = Field(default_factory=list)


class PlanDecisionFactor(BaseModel):
    factor: str
    assessment: str


class RecoveryPlan(BaseModel):
    recommended_flight_number: str
    decision_factors: list[PlanDecisionFactor]
    estimated_extra_cost: float
    requires_booking_change: bool
    requires_user_approval: bool
    confidence: float = Field(ge=0.0, le=1.0)


class PlannerOutput(BaseModel):
    plan_available: bool
    recommended_plan: Optional[RecoveryPlan] = None
    alternatives_considered: list[str] = Field(default_factory=list)
    no_plan_reason: Optional[str] = None


class PendingAction(BaseModel):
    action_type: ActionType
    description: str
    flight_number: Optional[str] = None
    additional_cost: Optional[float] = None
    requires_approval: bool = True


class ToolResult(BaseModel):
    success: bool
    data: Optional[dict | list] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False


class ActionRecord(BaseModel):
    action: str
    tool: Optional[str] = None
    success: bool
    details: Optional[str] = None


class EscalationOutput(BaseModel):
    escalation_required: bool
    reason: EscalationReason
    priority: Severity
    summary: str
    actions_attempted: list[str]
    recommended_human_action: str


class QAOutput(BaseModel):
    disruption_correctly_classified: bool
    traveler_constraints_respected: bool
    appropriate_tools_used: bool
    approval_obtained_when_required: bool
    unsupported_actions_attempted: bool
    unnecessary_tool_calls: int = Field(ge=0)
    resolution_status: ResolutionStatus
    follow_up_required: bool
    follow_up_reason: Optional[str] = None
    quality_score: float = Field(ge=0.0, le=1.0)
    summary: str
