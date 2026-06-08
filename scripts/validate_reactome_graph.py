#!/usr/bin/env python3
"""Validate Reactome import in Neo4j Aura."""
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
        checks = [
            ('Pathway', 'MATCH (n:Pathway) RETURN count(n) AS c'),
            ('Protein', 'MATCH (n:Protein) RETURN count(n) AS c'),
            ('PARTICIPATES_IN', 'MATCH ()-[r:PARTICIPATES_IN]->() RETURN count(r) AS c'),
        ]
        print('=== Reactome validation ===')
        for label, query in checks:
            res = client.run_query(query)
            count = res[0]['c'] if res else 0
            print(f'{label}: {count}')
        return 0
    except Exception as exc:
        print(f'Validation error: {exc}')
        return 1
    finally:
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
