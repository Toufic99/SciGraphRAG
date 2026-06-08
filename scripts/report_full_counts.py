#!/usr/bin/env python3
from pathlib import Path
import sys
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from kg.neo4j_client import Neo4jClient  # noqa: E402


def main() -> int:
    load_dotenv()
    client = Neo4jClient()
    try:
        client.connect()
        queries = [
            ('BiologicalProcess nodes', 'MATCH (n:BiologicalProcess) RETURN count(n) AS c'),
            ('Pathway nodes', 'MATCH (n:Pathway) RETURN count(n) AS c'),
            ('Protein nodes', 'MATCH (n:Protein) RETURN count(n) AS c'),
            ('IS_A relationships', 'MATCH ()-[r:IS_A]->() RETURN count(r) AS c'),
            ('PART_OF relationships', 'MATCH ()-[r:PART_OF]->() RETURN count(r) AS c'),
            ('PARTICIPATES_IN relationships', 'MATCH ()-[r:PARTICIPATES_IN]->() RETURN count(r) AS c'),
        ]
        print('=== Full KG counts ===')
        for label, query in queries:
            res = client.run_query(query)
            count = res[0]['c'] if res else 0
            print(f'{label}: {count}')
        return 0
    finally:
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
