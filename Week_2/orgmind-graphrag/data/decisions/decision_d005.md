---
doc_id: doc_decision_d005
doc_type: architecture_decision
entity_id: decision_d005
project_id: project_phoenix
date: 2026-04-11
---
# Use Kafka as Phoenix behavior event bus

**Decision ID:** decision_d005  
**Project:** Project Phoenix  
**Technology:** Kafka  
**Proposed by:** Carol Martinez  
**Approved by:** Farah Khan  
**Date:** 2026-04-11

## Decision
Use Kafka as Phoenix behavior event bus.

## Rationale
Recommendation features needed near-real-time user behavior with replay for backfills. Kafka aligned Phoenix with the company streaming standard.

## Alternatives considered
Batch files every hour, Point-to-point queues
