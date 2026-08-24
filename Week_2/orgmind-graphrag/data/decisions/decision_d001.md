---
doc_id: doc_decision_d001
doc_type: architecture_decision
entity_id: decision_d001
project_id: project_atlas
date: 2026-02-12
---
# Adopt Kafka for Atlas change feed

**Decision ID:** decision_d001  
**Project:** Project Atlas  
**Technology:** Kafka  
**Proposed by:** Carol Martinez  
**Approved by:** Alice Chen  
**Date:** 2026-02-12

## Decision
Adopt Kafka for Atlas change feed.

## Rationale
Atlas needed replayable, ordered product and behavior updates. Kafka provided durable event history and decoupled producers from ranking consumers.

## Alternatives considered
Direct database polling, Managed queue without replay
