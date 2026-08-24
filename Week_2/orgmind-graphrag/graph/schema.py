"""
Canonical graph schema for the Acme AI organizational GraphRAG project.

This file contains only normal Python data structures.
LlamaIndex-specific type conversions are done where the extractor is created.
"""


# -------------------------------------------------------------------
# Node definitions
# -------------------------------------------------------------------

NODE_SCHEMAS = {
    "Person": {
        "id_property": "id",
        "required": ["id", "name"],
        "optional": ["title"],
    },

    "Team": {
        "id_property": "id",
        "required": ["id", "name"],
        "optional": ["mission"],
    },

    "Project": {
        "id_property": "id",
        "required": ["id", "name"],
        "optional": ["purpose", "status"],
    },

    "Skill": {
        "id_property": "id",
        "required": ["id", "name"],
        "optional": [],
    },

    "Technology": {
        "id_property": "id",
        "required": ["id", "name"],
        "optional": [],
    },

    "Decision": {
        "id_property": "id",
        "required": ["id", "title"],
        "optional": ["date", "rationale"],
    },

    "Meeting": {
        "id_property": "id",
        "required": ["id", "title"],
        "optional": ["date"],
    },

    "Document": {
        "id_property": "id",
        "required": ["id", "title"],
        "optional": ["path", "doc_type", "date"],
    },
}


# -------------------------------------------------------------------
# Canonical relationship schema
#
# (source_entity, relationship, target_entity)
# -------------------------------------------------------------------

RELATIONSHIP_SCHEMAS = [
    ("Person", "MEMBER_OF", "Team"),
    ("Person", "HAS_SKILL", "Skill"),
    ("Person", "WORKED_ON", "Project"),
    ("Person", "LEADS", "Project"),

    ("Project", "OWNED_BY", "Team"),
    ("Project", "USES", "Technology"),

    ("Person", "PROPOSED", "Decision"),
    ("Person", "APPROVED", "Decision"),

    ("Decision", "AFFECTS", "Project"),
    ("Decision", "INVOLVES", "Technology"),

    ("Person", "ATTENDED", "Meeting"),
    ("Meeting", "DISCUSSED", "Decision"),

    ("Document", "DESCRIBES", "Project"),
    ("Document", "DOCUMENTS", "Decision"),
    ("Document", "MENTIONS", "Person"),

    ("Person", "AUTHORED", "Document"),
]


# -------------------------------------------------------------------
# Convenience lists
# -------------------------------------------------------------------

ENTITY_NAMES = list(NODE_SCHEMAS.keys())

RELATIONSHIP_NAMES = sorted({
    relationship
    for _, relationship, _ in RELATIONSHIP_SCHEMAS
})


# -------------------------------------------------------------------
# LlamaIndex SchemaLLMPathExtractor validation mapping
#
# This specifies which relationships may originate from each node type.
# -------------------------------------------------------------------

VALIDATION_SCHEMA = {
    "Person": [
        "MEMBER_OF",
        "HAS_SKILL",
        "WORKED_ON",
        "LEADS",
        "PROPOSED",
        "APPROVED",
        "ATTENDED",
        "AUTHORED",
    ],

    "Project": [
        "OWNED_BY",
        "USES",
    ],

    "Decision": [
        "AFFECTS",
        "INVOLVES",
    ],

    "Meeting": [
        "DISCUSSED",
    ],

    "Document": [
        "DESCRIBES",
        "DOCUMENTS",
        "MENTIONS",
    ],

    "Team": [],
    "Skill": [],
    "Technology": [],
}