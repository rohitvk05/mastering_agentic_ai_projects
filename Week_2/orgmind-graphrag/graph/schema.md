# Acme AI Graph Schema

## Nodes
`Person`, `Team`, `Project`, `Skill`, `Technology`, `Decision`, `Meeting`, `Document`

## Relationships

```text
(Person)-[:MEMBER_OF]->(Team)
(Person)-[:HAS_SKILL]->(Skill)
(Person)-[:WORKED_ON]->(Project)
(Person)-[:LEADS]->(Project)

(Project)-[:OWNED_BY]->(Team)
(Project)-[:USES]->(Technology)

(Person)-[:PROPOSED]->(Decision)
(Person)-[:APPROVED]->(Decision)
(Decision)-[:AFFECTS]->(Project)
(Decision)-[:INVOLVES]->(Technology)

(Person)-[:ATTENDED]->(Meeting)
(Meeting)-[:DISCUSSED]->(Decision)

(Document)-[:DESCRIBES]->(Project)
(Document)-[:DOCUMENTS]->(Decision)
(Document)-[:MENTIONS]->(Person)
(Person)-[:AUTHORED]->(Document)
```

### Design choice
`Skill` and `Technology` are deliberately separate. A person may have a skill without every project they work on using that technology, and a project may use a technology without every contributor being an expert in it.
