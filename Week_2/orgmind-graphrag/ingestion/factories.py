"""Shared LlamaIndex factories used by the reproducible ingestion CLIs."""

from typing import Literal

from llama_index.core import PromptTemplate
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.llms.openai_like import OpenAILike
from llama_index.vector_stores.neo4jvector import Neo4jVectorStore

from config import (
    NEBIUS_API_KEY,
    NEBIUS_BASE_URL,
    NEBIUS_MODEL,
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
)
from graph.schema import ENTITY_NAMES, RELATIONSHIP_NAMES, RELATIONSHIP_SCHEMAS


EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
VECTOR_INDEX_NAME = "orgmind_vector_index"
VECTOR_NODE_LABEL = "VectorChunk"

LLAMAINDEX_ENTITY_NAMES = [name.upper() for name in ENTITY_NAMES]
LLAMAINDEX_RELATIONSHIP_NAMES = [name.upper() for name in RELATIONSHIP_NAMES]
LLAMAINDEX_VALIDATION_SCHEMA = [
    (source.upper(), relationship.upper(), target.upper())
    for source, relationship, target in RELATIONSHIP_SCHEMAS
]

EntityTypes = Literal[tuple(LLAMAINDEX_ENTITY_NAMES)]
RelationTypes = Literal[tuple(LLAMAINDEX_RELATIONSHIP_NAMES)]


ORG_KG_EXTRACTION_PROMPT = PromptTemplate(
    """
Extract ALL explicitly stated knowledge graph relationships from the text using
only the supplied schema. Extract one relationship for every item in a list.
Never infer unstated facts and never use metadata IDs as entity names; use the
human-readable names in the document.

Project rules:
- Project lead -> PERSON --LEADS--> PROJECT
- Each contributor -> PERSON --WORKED_ON--> PROJECT
- Owning team -> PROJECT --OWNED_BY--> TEAM
- Each core technology -> PROJECT --USES--> TECHNOLOGY

Person rules:
- Team -> PERSON --MEMBER_OF--> TEAM
- Each skill -> PERSON --HAS_SKILL--> SKILL
- Each project -> PERSON --WORKED_ON--> PROJECT
- SKILL and TECHNOLOGY are distinct entity types.

Decision rules:
- Proposed by -> PERSON --PROPOSED--> DECISION
- Approved by -> PERSON --APPROVED--> DECISION
- Project -> DECISION --AFFECTS--> PROJECT
- Technology -> DECISION --INVOLVES--> TECHNOLOGY
- Use the human-readable decision title as the DECISION name.

Meeting rules:
- Use the heading as the MEETING name.
- Each participant -> PERSON --ATTENDED--> MEETING
- Each listed decision -> MEETING --DISCUSSED--> DECISION

Only create document relationships when explicitly supported. Extract up to
{max_triplets_per_chunk} relationships.

-------
{text}
-------
"""
)


def validate_service_configuration(require_llm: bool = False) -> None:
    missing = []
    if not NEO4J_URI:
        missing.append("NEO4J_URI")
    if not NEO4J_USERNAME:
        missing.append("NEO4J_USERNAME")
    if not NEO4J_PASSWORD:
        missing.append("NEO4J_PASSWORD")
    if require_llm and not NEBIUS_API_KEY:
        missing.append("NEBIUS_API_KEY")
    if missing:
        raise RuntimeError(f"Missing required environment values: {', '.join(missing)}")


def create_nebius_llm() -> OpenAILike:
    validate_service_configuration(require_llm=True)
    return OpenAILike(
        model=NEBIUS_MODEL,
        api_base=NEBIUS_BASE_URL,
        api_key=NEBIUS_API_KEY,
        is_chat_model=True,
        is_function_calling_model=False,
        should_use_structured_outputs=True,
        temperature=0.0,
        max_tokens=2000,
        context_window=16384,
    )


def create_embedding_model() -> HuggingFaceEmbedding:
    return HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)


def create_kg_extractor(
    llm: OpenAILike | None = None,
    max_triplets_per_chunk: int = 15,
) -> SchemaLLMPathExtractor:
    return SchemaLLMPathExtractor(
        llm=llm or create_nebius_llm(),
        extract_prompt=ORG_KG_EXTRACTION_PROMPT,
        possible_entities=EntityTypes,
        possible_relations=RelationTypes,
        kg_validation_schema=LLAMAINDEX_VALIDATION_SCHEMA,
        strict=True,
        allow_additional_properties=False,
        max_triplets_per_chunk=max_triplets_per_chunk,
        num_workers=1,
        raise_on_error=True,
    )


def create_graph_store() -> Neo4jPropertyGraphStore:
    validate_service_configuration()
    return Neo4jPropertyGraphStore(
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        url=NEO4J_URI,
        database=NEO4J_DATABASE,
    )


def create_vector_store(embedding_dimension: int) -> Neo4jVectorStore:
    validate_service_configuration()
    return Neo4jVectorStore(
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        url=NEO4J_URI,
        database=NEO4J_DATABASE,
        index_name=VECTOR_INDEX_NAME,
        node_label=VECTOR_NODE_LABEL,
        embedding_dimension=embedding_dimension,
        embedding_node_property="embedding",
        text_node_property="text",
    )
