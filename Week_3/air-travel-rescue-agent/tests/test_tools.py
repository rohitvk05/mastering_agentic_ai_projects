from src.tools.airport_tools import get_nearby_airports
from src.tools.booking_tools import get_booking_details, rebook_flight
from src.tools.flight_tools import get_flight_status, search_flights


def test_get_cancelled_flight_status():
    result = get_flight_status("UA900")
    assert result.success
    assert result.data["status"] == "cancelled"


def test_search_replacement_flights():
    result = search_flights("SFO", "LAS")
    assert result.success
    assert len(result.data) >= 1


def test_booking_lookup():
    result = get_booking_details("BR1001")
    assert result.success


def test_rebooking_requires_approval():
    result = rebook_flight("BR1001", "UA901", user_approved=False)
    assert not result.success
    assert result.error_type == "APPROVAL_REQUIRED"


def test_nearby_airports():
    result = get_nearby_airports("SFO")
    assert result.success
    assert "OAK" in result.data
