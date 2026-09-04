from src.models.schemas import EvaluatedFlight, FlightOption, RecoveryOutput

def recovery_agent(state):
    converted = []
    for option in state.get("evaluated_options", []):
        flight = FlightOption(**{
            k: v for k, v in option["flight"].items()
            if k in FlightOption.model_fields
        })
        converted.append(EvaluatedFlight(
            flight=flight,
            meets_deadline=option["meets_deadline"],
            within_budget=option["within_budget"],
            feasible=option["feasible"],
            rejection_reasons=option.get("rejection_reasons", []),
        ))

    viable_count = sum(x.feasible for x in converted)
    if not converted:
        notes = ["No alternative flights were returned."]
    elif viable_count == 0:
        notes = ["Alternative flights were found, but none satisfy the traveler constraints."]
    else:
        notes = [f"{viable_count} viable recovery option(s) found."]

    result = RecoveryOutput(
        evaluated_options=converted,
        viable_option_count=viable_count,
        recovery_possible=viable_count > 0,
        notes=notes,
    )
    return {"recovery_output": result}
