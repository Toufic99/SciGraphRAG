#!/usr/bin/env python3
"""Import Reactome subset into Neo4j Aura without modifying GO data.

Expected input files:
- data/processed/reactome_nodes.json
- data/processed/reactome_edges.json

Expected output:
- Proteins imported: X
- Pathways imported: Y
- PARTICIPATES_IN relationships: Z
- 5 example Protein -> PARTICIPATES_IN -> Pathway rows
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from kg.neo4j_client import Neo4jClient  # noqa: E402
from kg.schema import apply_schema  # noqa: E402


DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'processed'
NODES_FILE = DATA_DIR / 'reactome_nodes.json'
EDGES_FILE = DATA_DIR / 'reactome_edges.json'


def _load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f'Missing file: {path}')
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def _import_pathways(client: Neo4jClient, pathways: list[dict], batch_size: int = 100) -> int:
    query = """
    UNWIND $batch AS p
    MERGE (path:Pathway {id: p.id})
    SET path.name = p.name,
        path.source = p.source
    RETURN count(*) AS imported
    """
    total = 0
    for i in range(0, len(pathways), batch_size):
        batch = pathways[i:i + batch_size]
        res = client.run_query(query, {'batch': batch})
        total += res[0]['imported'] if res else 0
    return total


def _import_proteins(client: Neo4jClient, proteins: list[dict], batch_size: int = 100) -> int:
    query = """
    UNWIND $batch AS p
    MERGE (prot:Protein {uniprot: p.uniprot})
    SET prot.name = p.name
    RETURN count(*) AS imported
    """
    total = 0
    for i in range(0, len(proteins), batch_size):
        batch = proteins[i:i + batch_size]
        res = client.run_query(query, {'batch': batch})
        total += res[0]['imported'] if res else 0
    return total


def _import_edges(client: Neo4jClient, edges: list[dict], batch_size: int = 100) -> int:
    query = """
    UNWIND $batch AS e
    MATCH (prot:Protein {uniprot: e.source})
    MATCH (path:Pathway {id: e.target})
    MERGE (prot)-[:PARTICIPATES_IN]->(path)
    RETURN count(*) AS imported
    """
    total = 0
    for i in range(0, len(edges), batch_size):
        batch = edges[i:i + batch_size]
        res = client.run_query(query, {'batch': batch})
        total += res[0]['imported'] if res else 0
    return total


def _sample_examples(client: Neo4jClient, limit: int = 5):
    query = f"""
    MATCH (prot:Protein)-[:PARTICIPATES_IN]->(path:Pathway)
    RETURN prot.uniprot AS uniprot, prot.name AS protein, path.name AS pathway
    LIMIT {limit}
    """
    return client.run_query(query)


def main() -> int:
    load_dotenv()

    print('=== Reactome import ===')
    print(f'Nodes file: {NODES_FILE}')
    print(f'Edges file: {EDGES_FILE}')

    pathways_or_proteins = _load_json(NODES_FILE)
    edges = _load_json(EDGES_FILE)

    pathways = [n for n in pathways_or_proteins if n.get('type') == 'Pathway']
    proteins = [n for n in pathways_or_proteins if n.get('type') == 'Protein']

    print(f'Loaded {len(pathways)} pathways, {len(proteins)} proteins, {len(edges)} PARTICIPATES_IN edges')

    client = Neo4jClient()
    try:
        client.connect()
        apply_schema(client)

        imported_pathways = _import_pathways(client, pathways)
        imported_proteins = _import_proteins(client, proteins)
        imported_edges = _import_edges(client, edges)

        print(f'Pathways imported: {imported_pathways}')
        print(f'Proteins imported: {imported_proteins}')
        print(f'PARTICIPATES_IN relationships: {imported_edges}')
        print('\n=== 5 examples ===')
        rows = _sample_examples(client, 5)
        if rows:
            for row in rows:
                print(f"Protein {row.get('protein')} ({row.get('uniprot')}) -> PARTICIPATES_IN -> Pathway {row.get('pathway')}")
        else:
            print('No example rows found')
        return 0
    except Exception as exc:
        print(f'Error: {exc}')
        return 1
    finally:
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
