---
doc_id: doc_decision_d004
doc_type: architecture_decision
entity_id: decision_d004
project_id: project_phoenix
date: 2026-04-03
---
# Use Redis for Phoenix online feature cache

**Decision ID:** decision_d004  
**Project:** Project Phoenix  
**Technology:** Redis  
**Proposed by:** Bob Singh  
**Approved by:** Farah Khan  
**Date:** 2026-04-03

## Decision
Use Redis for Phoenix online feature cache.

## Rationale
Phoenix required predictable sub-20ms feature lookups during recommendation ranking. Redis met latency and operational requirements.

## Alternatives considered
Read directly from PostgreSQL, In-process cache only
