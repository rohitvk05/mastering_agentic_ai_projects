---
doc_id: doc_decision_d008
doc_type: architecture_decision
entity_id: decision_d008
project_id: project_mercury
date: 2026-05-29
---
# Use PostgreSQL as Mercury reconciliation ledger

**Decision ID:** decision_d008  
**Project:** Project Mercury  
**Technology:** PostgreSQL  
**Proposed by:** Elena Rossi  
**Approved by:** Julia Patel  
**Date:** 2026-05-29

## Decision
Use PostgreSQL as Mercury reconciliation ledger.

## Rationale
Mercury needed a transactional source of truth for settlement status, discrepancies, and audit trails.

## Alternatives considered
Object storage tables, Key-value store
