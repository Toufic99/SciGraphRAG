"""
cypher_templates.py

Simple Cypher templates to retrieve subgraphs for the demo queries.
"""

Q1 = """
MATCH path = (b:BiologicalProcess)-[:IS_A|:PART_OF*1..3]->(:BiologicalProcess)
WHERE toLower(b.label) CONTAINS $kw
RETURN nodes(path) AS nodes, relationships(path) AS rels
LIMIT 50
"""

Q2 = """
MATCH (p:Pathway)-[:INVOLVED_IN]->(b:BiologicalProcess)
WHERE toLower(p.name) CONTAINS $kw
RETURN p, b
LIMIT 30
"""

Q3 = """
MATCH (prot:Protein)-[:PARTICIPATES_IN]->(path:Pathway)-[:INVOLVED_IN]->(b:BiologicalProcess)
WHERE toLower(b.label) CONTAINS $kw
RETURN prot, path, b
LIMIT 40
"""


def run_query(client, template, kw):
    params = {'kw': kw.lower()}
    rows = client.run_query(template, params)
    # client.run_query returns records; higher-level processing should serialize nodes/rels
    return rows
