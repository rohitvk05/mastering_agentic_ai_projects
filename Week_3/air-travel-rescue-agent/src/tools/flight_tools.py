import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from src.models.schemas import FlightOption, ToolResult

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_flights() -> list[dict]:
    with open(DATA_DIR / "flights.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_flight_status(flight_number: str) -> ToolResult:
    flights = _load_flights()
    for flight in flights:
        if flight["flight_number"].upper() == flight_number.upper():
            return ToolResult(success=True, data=flight)
    return ToolResult(
        success=False,
        error_type="FLIGHT_NOT_FOUND",
        error_message=f"Flight {flight_number} not found.",
        retryable=False,
    )


def search_flights(
    origin: str,
    destination: str,
    arrival_before: Optional[str] = None,
    simulate_failure: bool = False,
) -> ToolResult:

    if simulate_failure:
        return ToolResult(
            success=False,
            error_type="SERVICE_UNAVAILABLE",
            error_message="Flight inventory service is temporarily unavailable.",
            retryable=True,
        )

    flights = _load_flights()

    matches = [
        f for f in flights
        if f["origin"].upper() == origin.upper()
        and f["destination"].upper() == destination.upper()
        and f["status"] == "scheduled"
        and f["available_seats"] > 0
    ]

    if arrival_before:
        matches = [
            f for f in matches
            if f["arrival_time"] <= arrival_before
        ]

    return ToolResult(
        success=True,
        data=matches
    )

def evaluate_flight_options(
    flights: list[dict],
    arrival_deadline: Optional[str] = None,
    max_extra_cost: Optional[float] = None,
) -> list[dict]:

    evaluated = []

    deadline_dt = (
        datetime.fromisoformat(arrival_deadline)
        if arrival_deadline
        else None
    )

    for flight in flights:

        arrival_dt = datetime.fromisoformat(
            flight["arrival_time"]
        )

        meets_deadline = (
            True
            if deadline_dt is None
            else arrival_dt <= deadline_dt
        )

        within_budget = (
            True
            if max_extra_cost is None
            else flight["fare_difference"] <= max_extra_cost
        )

        has_seats = flight["available_seats"] > 0

        feasible = (
            meets_deadline
            and within_budget
            and has_seats
        )

        rejection_reasons = []

        if not meets_deadline:
            rejection_reasons.append(
                "Arrives after traveler deadline"
            )

        if not within_budget:
            rejection_reasons.append(
                "Exceeds traveler budget"
            )

        if not has_seats:
            rejection_reasons.append(
                "No available seats"
            )

        evaluated.append({
            "flight": flight,
            "meets_deadline": meets_deadline,
            "within_budget": within_budget,
            "has_seats": has_seats,
            "feasible": feasible,
            "rejection_reasons": rejection_reasons,
        })

    return evaluated

def rank_flight_options(evaluated_options: list[dict]) -> list[dict]:
    viable = [
        x for x in evaluated_options
        if x["feasible"]
    ]

    return sorted(
        viable,
        key=lambda x: (
            x["flight"]["stops"],
            x["flight"]["fare_difference"],
            x["flight"]["arrival_time"],
        )
    )
