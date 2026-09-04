from src.models.schemas import IntakeOutput


def intake_agent(state, intake_chain):
    # Re-read the complete traveler history so follow-up answers can fill
    # details that were missing from the original request.
    traveler_message = "\n".join(
        str(message.content)
        for message in state["messages"]
    )

    result: IntakeOutput = intake_chain.invoke({
        "traveler_message": traveler_message
    })

    return {
        "origin": result.origin,
        "destination": result.destination,
        "flight_number": result.flight_number,
        "travel_date": result.travel_date,
        "booking_id": result.booking_id,
        "issue_description": result.issue_description,
        "arrival_deadline": result.arrival_deadline,
        "max_extra_cost": result.max_extra_cost,
        "preferences": result.preferences,
        "missing_information": result.missing_information,
    }
