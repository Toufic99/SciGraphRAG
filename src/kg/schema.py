"""
schema.py

Neo4j schema: constraints and indexes for BiologicalProcess, Pathway, Protein
"""

CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (b:BiologicalProcess) REQUIRE b.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Pathway) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (pr:Protein) REQUIRE pr.uniprot IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (b:BiologicalProcess) ON (b.label)",
    "CREATE INDEX IF NOT EXISTS FOR (p:Pathway) ON (p.name)",
    "CREATE INDEX IF NOT EXISTS FOR (pr:Protein) ON (pr.name)",
]


def apply_schema(client):
    """Apply constraints and indexes using a Neo4j client with run_query method."""
    for q in CONSTRAINTS + INDEXES:
        print(f"Applying: {q}")
        client.run_query(q)
