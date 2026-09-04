from src.models.schemas import PlannerOutput


def planner_agent(state, planner_chain):

    rejected_flights = set(
        state.get("rejected_flights", [])
    )

    # Final safety filter:
    # the Planner must never see a flight the traveler rejected.
    ranked_options = [
        option
        for option in state.get("ranked_options", [])
        if option["flight"]["flight_number"]
        not in rejected_flights
    ]

    # No options remain -> graph will route to escalation.
    if not ranked_options:
        return {
            "planner_output": None,
            "recommended_plan": None,
            "ranked_options": [],
        }

    planner_options = []

    for option in ranked_options:
        flight = option["flight"]

        planner_options.append({
            "flight_number": flight["flight_number"],
            "airline": flight["airline"],
            "origin": flight["origin"],
            "destination": flight["destination"],
            "departure_time": flight["departure_time"],
            "arrival_time": flight["arrival_time"],
            "stops": flight["stops"],
            "fare_difference": flight["fare_difference"],
            "available_seats": flight["available_seats"],
        })

    result: PlannerOutput = planner_chain.invoke({
        "origin": state.get("origin"),
        "destination": state.get("destination"),
        "arrival_deadline": state.get("arrival_deadline"),
        "max_extra_cost": state.get("max_extra_cost"),
        "preferences": state.get("preferences", []),
        "ranked_options": planner_options,
    })

    valid_flights = {
        option["flight"]["flight_number"]
        for option in ranked_options
    }

    if result.plan_available and result.recommended_plan:
        recommended = (
            result.recommended_plan.recommended_flight_number
        )

        # LLM must only select currently allowed flights.
        if recommended not in valid_flights:
            raise ValueError(
                f"Planner selected invalid or rejected flight: "
                f"{recommended}. "
                f"Allowed flights: {sorted(valid_flights)}"
            )

        if recommended in rejected_flights:
            raise ValueError(
                f"Planner attempted to reuse rejected flight: "
                f"{recommended}"
            )

    return {
        # Persist the filtered candidate pool too.
        "ranked_options": ranked_options,
        "planner_output": result,
        "recommended_plan": result.recommended_plan,
    }