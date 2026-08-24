---
doc_id: doc_tech_search_architecture
doc_type: technical_document
owner: Search
---
# Search Architecture Overview

Project Atlas is the Search team's modernization program for product retrieval and ranking. Alice Chen leads the project.

Atlas uses Elasticsearch as the retrieval engine, Python for ranking services, Kafka for change feeds, and Kubernetes for service deployment. George Liu owns index mapping and analyzer design. Alice Chen approved the Kafka, Elasticsearch, and Kubernetes architecture decisions for Atlas.
