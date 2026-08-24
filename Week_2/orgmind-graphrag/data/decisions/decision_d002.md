---
doc_id: doc_decision_d002
doc_type: architecture_decision
entity_id: decision_d002
project_id: project_atlas
date: 2026-02-28
---
# Standardize Elasticsearch mappings for Atlas

**Decision ID:** decision_d002  
**Project:** Project Atlas  
**Technology:** Elasticsearch  
**Proposed by:** George Liu  
**Approved by:** Alice Chen  
**Date:** 2026-02-28

## Decision
Standardize Elasticsearch mappings for Atlas.

## Rationale
Inconsistent field mappings caused relevance drift across indexes. A shared template made analyzers and ranking fields predictable.

## Alternatives considered
Per-index mappings, Schema-on-read
