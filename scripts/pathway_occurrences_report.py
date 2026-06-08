#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from kg.neo4j_client import Neo4jClient  # noqa: E402


def main() -> int:
    load_dotenv()
    client = Neo4jClient()
    try:
        client.connect()

        print('=== Pathway ID + Name + Occurrences ===')
        rows = client.run_query(
            '''
            MATCH (p:Pathway)
            RETURN p.id AS pathway_id, p.name AS pathway_name, count(*) AS occurrences
            ORDER BY pathway_id ASC
            '''
        )
        for row in rows:
            print(f"{row['pathway_id']} | {row['pathway_name']} | {row['occurrences']}")

        print('\n=== Relationship Coherence Checks ===')
        summary = client.run_query(
            '''
            MATCH (p:Pathway)
            WITH collect(p) AS pathways
            MATCH ()-[r:PARTICIPATES_IN]->(pw:Pathway)
            WITH pathways, count(r) AS total_rel,
                 count(CASE WHEN pw.id STARTS WITH 'R-HSA-' THEN 1 END) AS rel_to_stable,
                 count(CASE WHEN pw.id STARTS WITH 'Pathway' THEN 1 END) AS rel_to_local
            RETURN total_rel, rel_to_stable, rel_to_local
            '''
        )[0]
        print(f"PARTICIPATES_IN total: {summary['total_rel']}")
        print(f"PARTICIPATES_IN to stable Pathway IDs (R-HSA-*): {summary['rel_to_stable']}")
        print(f"PARTICIPATES_IN to local Pathway IDs (Pathway*): {summary['rel_to_local']}")

        distinct_cov = client.run_query(
            '''
            MATCH (p:Pathway)
                        OPTIONAL MATCH (:Protein)-[r:PARTICIPATES_IN]->(p)
                        WITH p, count(r) AS rel_count
            RETURN
              count(p) AS pathways_total,
              count(CASE WHEN rel_count = 0 THEN 1 END) AS pathways_without_rel,
              count(CASE WHEN rel_count > 0 THEN 1 END) AS pathways_with_rel
            '''
        )[0]
        print(f"Pathways total: {distinct_cov['pathways_total']}")
        print(f"Pathways with >=1 PARTICIPATES_IN: {distinct_cov['pathways_with_rel']}")
        print(f"Pathways with 0 PARTICIPATES_IN: {distinct_cov['pathways_without_rel']}")

        return 0
    finally:
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
