# Air Travel Rescue Agent

A multi-agent, stateful voice assistant for helping air travelers recover from flight disruptions such as cancellations, delays, missed connections, and schedule changes.

## Project Goal

The system is designed to:
- understand a traveler disruption,
- extract trip details and constraints,
- classify the disruption,
- search viable recovery options,
- recommend the best plan,
- require human approval before write actions such as rebooking,
- recover from tool failures,
- escalate when automation should stop,
- generate a structured QA review after the interaction.

## Architecture

Traveler -> ElevenLabs Voice -> LangGraph Orchestrator -> Specialized Agents -> Tools -> HITL Approval -> Resolution / Escalation -> QA

### Agents
1. Intake Agent
2. Triage Agent
3. Recovery Agent
4. Recovery Planner Agent
5. Escalation Agent
6. QA Agent

### Core Tools
- get_flight_status
- search_flights
- get_booking_details
- get_nearby_airports
- rebook_flight
- create_support_case

## Design Principles

- LLMs reason and interpret.
- Python handles deterministic validation, arithmetic, routing, retries, and state transitions.
- Tools retrieve or modify external state.
- LangGraph owns orchestration and shared state.
- All write actions require explicit human approval.

## Initial Demo Scenarios

1. Successful cancellation recovery
2. Recovery under arrival deadline
3. Missed connection
4. Retryable tool failure
5. No viable recovery -> escalation

## Setup

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

## Development Order

1. Synthetic airline datasets
2. Deterministic tools
3. Pydantic schemas
4. LangGraph state
5. Agent nodes
6. Routing + retries
7. Human-in-the-loop
8. Evaluation scenarios
9. ElevenLabs voice integration


## Synthetic Dataset

The repo now ships with a larger repeatable airline environment:

- `241` flight records across `26` route patterns and multiple airlines
- `30` traveler bookings
- `12` traveler profiles
- `21` airports with nearby-airport relationships and connection rules
- `5` airline/support policy records
- 5 acceptance/demo scenarios
- empty support-case store for simulated escalation writes

The data is synthetic so the demo remains deterministic and does not depend on live airline availability.
