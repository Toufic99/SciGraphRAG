#!/usr/bin/env python3
"""
scripts/validate_go_graph.py

Validate GO graph import with three Cypher queries:
  1. Count BiologicalProcess nodes
  2. Count IS_A relationships
  3. Count PART_OF relationships

Usage:
    python scripts/validate_go_graph.py

Requires:
    - .env file with NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    - GO data already imported into Neo4j
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kg.neo4j_client import Neo4jClient
from dotenv import load_dotenv


def main():
    # Load environment
    load_dotenv()
    
    print('=' * 60)
    print('Validating GO Graph in Neo4j')
    print('=' * 60)
    
    # Create and connect client
    client = Neo4jClient()
    
    print('\nConnecting to Neo4j...')
    try:
        client.connect()
        result = client.run_query('RETURN "Connected" AS status')
        if result:
            print('✅ Connected\n')
        else:
            print('❌ Connection failed')
            sys.exit(1)
    except Exception as e:
        print(f'❌ Connection failed: {e}')
        print('\nPlease verify .env file contains:')
        print('  NEO4J_URI=neo4j+s://...')
        print('  NEO4J_USER=neo4j')
        print('  NEO4J_PASSWORD=...')
        sys.exit(1)
    
    # Query 1: Count BiologicalProcess nodes
    print('Query a) MATCH (n:BiologicalProcess) RETURN count(n)')
    try:
        result = client.run_query('MATCH (n:BiologicalProcess) RETURN count(n) AS count')
        count = result[0]['count'] if result else 0
        print(f'Result: {count} BiologicalProcess nodes\n')
    except Exception as e:
        print(f'❌ Error: {e}\n')
        client.close()
        sys.exit(1)
    
    # Query 2: Count IS_A relationships
    print('Query b) MATCH ()-[r:IS_A]->() RETURN count(r)')
    try:
        result = client.run_query('MATCH ()-[r:IS_A]->() RETURN count(r) AS count')
        count = result[0]['count'] if result else 0
        print(f'Result: {count} IS_A relationships\n')
    except Exception as e:
        print(f'❌ Error: {e}\n')
        client.close()
        sys.exit(1)
    
    # Query 3: Count PART_OF relationships
    print('Query c) MATCH ()-[r:PART_OF]->() RETURN count(r)')
    try:
        result = client.run_query('MATCH ()-[r:PART_OF]->() RETURN count(r) AS count')
        count = result[0]['count'] if result else 0
        print(f'Result: {count} PART_OF relationships\n')
    except Exception as e:
        print(f'❌ Error: {e}\n')
        client.close()
        sys.exit(1)
    
    client.close()
    print('=' * 60)
    print('✅ Validation complete')
    print('=' * 60)


if __name__ == '__main__':
    main()
