---
doc_id: doc_decision_d003
doc_type: architecture_decision
entity_id: decision_d003
project_id: project_atlas
date: 2026-03-15
---
# Deploy Atlas ranking services on Kubernetes

**Decision ID:** decision_d003  
**Project:** Project Atlas  
**Technology:** Kubernetes  
**Proposed by:** Hannah Brooks  
**Approved by:** Alice Chen  
**Date:** 2026-03-15

## Decision
Deploy Atlas ranking services on Kubernetes.

## Rationale
The team needed controlled rollouts, autoscaling, and standard health checks for ranking services.

## Alternatives considered
Long-running VMs, Serverless functions
