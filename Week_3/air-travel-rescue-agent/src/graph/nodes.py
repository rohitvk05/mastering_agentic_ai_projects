from src.models.schemas import (
    ActionRecord, ActionType, ApprovalStatus, PendingAction, ResolutionStatus
)
from src.tools.booking_tools import get_booking_details, rebook_flight
from src.tools.flight_tools import get_flight_status, search_flights, evaluate_flight_options

def flight_recovery_node(state):
    """
    Verify the disrupted itinerary, search replacement flights,
    evaluate deterministic constraints, and rank viable options.

    If a valid booking ID is available, the booking record is treated
    as the authoritative source for flight number and route. This
    protects the voice workflow from transcription errors such as
    UA900 being heard as UN900.
    """

    spoken_flight_number = state.get("flight_number")
    booking_id = state.get("booking_id")

    action_history = []

    # --------------------------------------------------
    # 1. Resolve itinerary from booking when possible
    # --------------------------------------------------

    resolved_flight_number = spoken_flight_number
    resolved_origin = state.get("origin")
    resolved_destination = state.get("destination")

    if booking_id:
        booking_result = get_booking_details(
            booking_id
        )

        if booking_result.success:
            booking = booking_result.data

            booking_flight_number = booking.get(
                "flight_number"
            )

            if booking_flight_number:
                resolved_flight_number = (
                    booking_flight_number
                )

            resolved_origin = (
                booking.get("origin")
                or resolved_origin
            )

            resolved_destination = (
                booking.get("destination")
                or resolved_destination
            )

            details = (
                f"Booking {booking_id} resolved to "
                f"flight {resolved_flight_number}."
            )

            # Useful audit signal when speech transcription
            # disagrees with the actual booking.
            if (
                spoken_flight_number
                and booking_flight_number
                and spoken_flight_number.upper()
                != booking_flight_number.upper()
            ):
                details += (
                    f" Traveler input contained "
                    f"{spoken_flight_number}; "
                    f"booking record was used as "
                    f"the authoritative source."
                )

            action_history.append(
                ActionRecord(
                    action="resolved_booking_itinerary",
                    tool="get_booking_details",
                    success=True,
                    details=details,
                )
            )

        else:
            action_history.append(
                ActionRecord(
                    action="resolved_booking_itinerary",
                    tool="get_booking_details",
                    success=False,
                    details=booking_result.error_message,
                )
            )

    # --------------------------------------------------
    # 2. We still need a usable flight number
    # --------------------------------------------------

    if not resolved_flight_number:
        return {
            "last_error": (
                "Unable to determine the original flight number."
            ),
            "action_history": action_history,
        }

    # --------------------------------------------------
    # 3. Verify original flight
    # --------------------------------------------------

    status_result = get_flight_status(
        resolved_flight_number
    )

    if not status_result.success:
        action_history.append(
            ActionRecord(
                action="checked_original_flight",
                tool="get_flight_status",
                success=False,
                details=status_result.error_message,
            )
        )

        return {
            # Persist any booking-based correction.
            "flight_number":
                resolved_flight_number,

            "origin":
                resolved_origin,

            "destination":
                resolved_destination,

            "last_tool_result":
                status_result,

            "last_error":
                status_result.error_message,

            "action_history":
                action_history,
        }

    original_flight = status_result.data

    action_history.append(
        ActionRecord(
            action="checked_original_flight",
            tool="get_flight_status",
            success=True,
            details=(
                f"{resolved_flight_number} status: "
                f"{original_flight['status']}"
            ),
        )
    )

    # --------------------------------------------------
    # 4. Simulated failure behavior
    # --------------------------------------------------

    simulate_failure = (
        state.get(
            "simulate_persistent_search_failure",
            False,
        )
        or state.get(
            "simulate_search_failure",
            False,
        )
    )

    # --------------------------------------------------
    # 5. Search alternatives
    # --------------------------------------------------

    search_result = search_flights(
        origin=resolved_origin,
        destination=resolved_destination,
        simulate_failure=simulate_failure,
    )

    if not search_result.success:
        action_history.append(
            ActionRecord(
                action="searched_recovery_flights",
                tool="search_flights",
                success=False,
                details=search_result.error_message,
            )
        )

        return {
            "flight_number":
                resolved_flight_number,

            "origin":
                resolved_origin,

            "destination":
                resolved_destination,

            "original_flight":
                original_flight,

            "last_tool_result":
                search_result,

            "last_error":
                search_result.error_message,

            # transient failure is consumed
            "simulate_search_failure":
                False,

            # persistent failure stays active
            "simulate_persistent_search_failure":
                state.get(
                    "simulate_persistent_search_failure",
                    False,
                ),

            "action_history":
                action_history,
        }

    # --------------------------------------------------
    # 6. Deterministic feasibility evaluation
    # --------------------------------------------------

    evaluated = evaluate_flight_options(
        search_result.data,
        arrival_deadline=state.get(
            "arrival_deadline"
        ),
        max_extra_cost=state.get(
            "max_extra_cost"
        ),
    )

    viable = [
        option
        for option in evaluated
        if option["feasible"]
    ]

    # --------------------------------------------------
    # 7. Deterministic ranking
    # --------------------------------------------------

    ranked = sorted(
        viable,
        key=lambda option: (
            option["flight"]["stops"],
            option["flight"]["fare_difference"],
            option["flight"]["arrival_time"],
        ),
    )

    action_history.append(
        ActionRecord(
            action="searched_recovery_flights",
            tool="search_flights",
            success=True,
            details=(
                f"{len(search_result.data)} "
                f"alternatives returned; "
                f"{len(ranked)} viable."
            ),
        )
    )

    # --------------------------------------------------
    # 8. Return graph state update
    # --------------------------------------------------

    return {
        # Correct potentially mistranscribed values
        "flight_number":
            resolved_flight_number,

        "origin":
            resolved_origin,

        "destination":
            resolved_destination,

        "original_flight":
            original_flight,

        "alternative_flights":
            search_result.data,

        "evaluated_options":
            evaluated,

        "ranked_options":
            ranked,

        "last_tool_result":
            search_result,

        "last_error":
            None,

        "simulate_search_failure":
            False,

        "simulate_persistent_search_failure":
            state.get(
                "simulate_persistent_search_failure",
                False,
            ),

        "action_history":
            action_history,
    }

def retry_handler_node(state):
    return {"retry_count": state.get("retry_count", 0) + 1}

def create_pending_action_node(state):
    plan = state.get("recommended_plan")
    if not plan:
        return {
            "pending_action": None,
            "approval_status": ApprovalStatus.NOT_REQUIRED,
        }

    return {
        "pending_action": PendingAction(
            action_type=ActionType.REBOOK_FLIGHT,
            description=f"Rebook traveler onto {plan.recommended_flight_number}",
            flight_number=plan.recommended_flight_number,
            additional_cost=plan.estimated_extra_cost,
            requires_approval=True,
        ),
        "approval_status": ApprovalStatus.PENDING,
    }

def validate_booking_node(state):
    if not state.get("booking_id"):
        return {
            "last_error": "Booking ID is required before rebooking.",
            "escalation_required": False,
        }
    return {"last_error": None}

def execute_rebooking_node(state):
    if state.get("approval_status") != ApprovalStatus.APPROVED:
        return {
            "booking_updated": False,
            "action_history": [ActionRecord(
                action="rebooking_skipped",
                tool="rebook_flight",
                success=False,
                details="Traveler approval was not granted.",
            )],
        }

    result = rebook_flight(
        booking_id=state["booking_id"],
        new_flight_number=state["pending_action"].flight_number,
        user_approved=True,
    )

    return {
        "last_tool_result": result,
        "booking_updated": result.success,
        "last_error": None if result.success else result.error_message,
        "action_history": [ActionRecord(
            action="rebooked_flight",
            tool="rebook_flight",
            success=result.success,
            details=(
                f"Rebooked onto {state['pending_action'].flight_number}"
                if result.success else result.error_message
            ),
        )],
    }

def resolution_check_node(state):
    if state.get("booking_updated"):
        return {
            "resolution_status": ResolutionStatus.RESOLVED,
            "resolution_summary": (
                f"Traveler successfully rebooked onto "
                f"{state['pending_action'].flight_number}."
            ),
        }
    return {
        "resolution_status": ResolutionStatus.IN_PROGRESS,
        "resolution_summary": None,
    }

def handle_rejection_node(state):
    """
    Traveler rejected the currently proposed flight.

    Remove that option from consideration and allow
    the Planner Agent to choose the next-best option.
    """

    pending_action = state.get("pending_action")

    rejected_flights = list(
        state.get("rejected_flights", [])
    )

    if (
        pending_action
        and pending_action.flight_number
        and pending_action.flight_number not in rejected_flights
    ):
        rejected_flights.append(
            pending_action.flight_number
        )

    remaining_options = [
        option
        for option in state.get("ranked_options", [])
        if option["flight"]["flight_number"]
        not in rejected_flights
    ]

    return {
        "rejected_flights": rejected_flights,
        "rejection_count": state.get("rejection_count", 0) + 1,

        # Planner should only see remaining choices
        "ranked_options": remaining_options,

        # Clear previous recommendation
        "recommended_plan": None,
        "planner_output": None,
        "pending_action": None,

        # Prepare for another approval round
        "approval_status": ApprovalStatus.PENDING,

        "action_history": [
            ActionRecord(
                action="rejected_recovery_option",
                tool=None,
                success=True,
                details=(
                    f"Traveler rejected flight "
                    f"{pending_action.flight_number}"
                    if pending_action
                    else "Traveler rejected the proposed recovery option."
                ),
            )
        ],
    }
