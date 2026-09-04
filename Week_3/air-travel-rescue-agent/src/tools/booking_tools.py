import json
from pathlib import Path

from src.models.schemas import ToolResult

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_bookings() -> list[dict]:
    with open(DATA_DIR / "bookings.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _save_bookings(bookings: list[dict]) -> None:
    with open(DATA_DIR / "bookings.json", "w", encoding="utf-8") as f:
        json.dump(bookings, f, indent=2)


def get_booking_details(booking_id: str) -> ToolResult:
    bookings = _load_bookings()
    for booking in bookings:
        if booking["booking_id"].upper() == booking_id.upper():
            return ToolResult(success=True, data=booking)

    return ToolResult(
        success=False,
        error_type="INVALID_BOOKING",
        error_message="Booking ID could not be found.",
        retryable=False,
    )


def rebook_flight(
    booking_id: str,
    new_flight_number: str,
    user_approved: bool,
) -> ToolResult:
    if not user_approved:
        return ToolResult(
            success=False,
            error_type="APPROVAL_REQUIRED",
            error_message="Explicit traveler approval is required before rebooking.",
            retryable=False,
        )

    bookings = _load_bookings()

    for booking in bookings:
        if booking["booking_id"].upper() == booking_id.upper():
            booking["flight_number"] = new_flight_number.upper()
            booking["status"] = "rebooked"
            _save_bookings(bookings)
            return ToolResult(success=True, data=booking)

    return ToolResult(
        success=False,
        error_type="INVALID_BOOKING",
        error_message="Booking ID could not be found.",
        retryable=False,
    )
