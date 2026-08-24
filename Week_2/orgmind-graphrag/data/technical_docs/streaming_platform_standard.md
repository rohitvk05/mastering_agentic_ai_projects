---
doc_id: doc_tech_streaming_standard
doc_type: technical_document
owner: Data Platform
---
# Streaming Platform Standard

Acme AI standardizes high-volume event streaming on Kafka when replay, ordered partitions, and multiple independent consumers are required.

Carol Martinez is the primary technical contact for Kafka architecture. She proposed the Kafka decisions for both Project Atlas and Project Phoenix and maintains the organization-wide streaming guidance.

Project Atlas uses Kafka for product and behavioral changes. Project Phoenix uses Kafka for near-real-time behavior events. Project Nova also consumes Kafka events for risk signals, while Project Mercury publishes settlement events.
