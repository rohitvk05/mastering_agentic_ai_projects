---
doc_id: doc_tech_recommendation_architecture
doc_type: technical_document
owner: Recommendations
---
# Recommendation Architecture Overview

Project Phoenix serves real-time personalized recommendations. Farah Khan leads the project.

Phoenix uses Kafka for behavior events, Redis for online feature caching, Kubernetes for serving, and Python for model and service code. Bob Singh proposed Redis for the online feature cache. Carol Martinez proposed Kafka for the event bus. Farah Khan approved both decisions.
