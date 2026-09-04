# Acceptance Scenarios

## Scenario 1 — Successful recovery
UA900 SFO->LAS is cancelled. UA901 is viable. Traveler approves rebooking.

## Scenario 2 — Arrival deadline
Traveler must reach LAS before 11:00 AM the next day. Planner must reject options outside the deadline.

## Scenario 3 — Missed connection
Later dataset extension: delayed inbound flight creates an impossible connection.

## Scenario 4 — Retryable tool failure
Inject a temporary SERVICE_UNAVAILABLE result and test retry routing.

## Scenario 5 — No viable recovery
Remove seat availability from all suitable flights and verify escalation.
