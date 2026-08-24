---
doc_id: doc_decision_d007
doc_type: architecture_decision
entity_id: decision_d007
project_id: project_mercury
date: 2026-05-22
---
# Use Airflow for Mercury settlement workflows

**Decision ID:** decision_d007  
**Project:** Project Mercury  
**Technology:** Airflow  
**Proposed by:** Elena Rossi  
**Approved by:** Julia Patel  
**Date:** 2026-05-22

## Decision
Use Airflow for Mercury settlement workflows.

## Rationale
Settlement jobs have dependencies, retries, and cutoff windows. Airflow made orchestration and operational visibility explicit.

## Alternatives considered
Cron jobs, Custom scheduler
