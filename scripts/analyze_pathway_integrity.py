#!/usr/bin/env python3
"""Analyze Pathway integrity without modifying data."""
from __future__ import annotations

import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from kg.neo4j_client import Neo4jClient  # noqa: E402


def q(client: Neo4jClient, query: str):
    return client.run_query(query)


def main() -> int:
    load_dotenv()
    client = Neo4jClient()
    try:
        client.connect()

        print('=== Pathway Integrity Analysis ===')

        total = q(client, 'MATCH (p:Pathway) RETURN count(p) AS c')[0]['c']
        print(f'Total Pathway nodes: {total}')

        dup_names = q(
            client,
            '''
            MATCH (p:Pathway)
            WITH p.name AS pathway_name, collect(p.id) AS ids, count(*) AS occurrences
            WHERE occurrences > 1
            RETURN pathway_name, ids, occurrences
            ORDER BY occurrences DESC, pathway_name ASC
            '''
        )

        print('\nPotential duplicates by name (same name, multiple IDs):')
        if not dup_names:
            print('None')
        else:
            for row in dup_names:
                print(f"- Pathway name: {row['pathway_name']}")
                print(f"  Occurrences: {row['occurrences']}")
                print(f"  IDs: {', '.join(row['ids'])}")

        by_source = q(
            client,
            '''
            MATCH (p:Pathway)
            WITH
              CASE
                WHEN p.id STARTS WITH 'R-HSA-' THEN 'reactome_stable_id'
                WHEN p.id STARTS WITH 'Pathway' THEN 'local_biopax_id'
                ELSE 'other'
              END AS id_type,
              count(*) AS c
            RETURN id_type, c
            ORDER BY c DESC
            '''
        )

        print('\nPathway ID profile:')
        for row in by_source:
            print(f"- {row['id_type']}: {row['c']}")

        rel_total = q(client, 'MATCH ()-[r:PARTICIPATES_IN]->(:Pathway) RETURN count(r) AS c')[0]['c']
        print(f'\nTotal PARTICIPATES_IN: {rel_total}')

        pathway_rel_coverage = q(
            client,
            '''
            MATCH (p:Pathway)
            OPTIONAL MATCH (:Protein)-[r:PARTICIPATES_IN]->(p)
            RETURN
              count(p) AS pathways_total,
              count(CASE WHEN r IS NULL THEN 1 END) AS pathways_without_rel,
              count(CASE WHEN r IS NOT NULL THEN 1 END) AS pathways_with_rel
            '''
        )[0]

        print('Pathway relation coverage:')
        print(f"- Pathways with at least one PARTICIPATES_IN: {pathway_rel_coverage['pathways_with_rel']}")
        print(f"- Pathways without PARTICIPATES_IN: {pathway_rel_coverage['pathways_without_rel']}")

        no_rel = q(
            client,
            '''
            MATCH (p:Pathway)
            WHERE NOT ( (:Protein)-[:PARTICIPATES_IN]->(p) )
            RETURN p.id AS pathway_id, p.name AS pathway_name
            ORDER BY pathway_name ASC
            LIMIT 20
            '''
        )

        if no_rel:
            print('\nSample pathways without PARTICIPATES_IN (possible old import):')
            for row in no_rel:
                print(f"- {row['pathway_id']} | {row['pathway_name']}")

        return 0
    finally:
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
