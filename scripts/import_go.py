#!/usr/bin/env python3
"""
scripts/import_go.py

Complete GO import pipeline:
  1. Load .env credentials
  2. Connect to Neo4j
  3. Create constraints and indexes
  4. Import go_nodes.json (BiologicalProcess)
  5. Import go_edges.json (IS_A, PART_OF relationships)
  6. Display summary statistics

Usage:
    python scripts/import_go.py

Requires:
    - .env file with NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    - data/processed/go_nodes.json
    - data/processed/go_edges.json
"""

import sys
import os
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kg.neo4j_client import Neo4jClient
from kg.schema import CONSTRAINTS, INDEXES
from dotenv import load_dotenv


def main():
    # Load environment
    load_dotenv()
    
    print('=' * 60)
    print('GO Import to Neo4j')
    print('=' * 60)
    
    # Create client
    client = Neo4jClient()
    
    # Connect
    print('\nConnecting to Neo4j...')
    try:
        client.connect()
        result = client.run_query('RETURN "Connected" AS status')
        if result:
            print('✅ Connected to Neo4j\n')
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
    
    # Create constraints
    print('Creating constraints and indexes...')
    try:
        for constraint in CONSTRAINTS:
            client.run_query(constraint)
        for index in INDEXES:
            client.run_query(index)
        print('✅ Constraints created\n')
    except Exception as e:
        print(f'⚠️  Warning creating constraints: {e}')
        print('   Continuing anyway...\n')
    
    # Load data files
    print('Loading data files...')
    nodes_path = 'data/processed/go_nodes.json'
    edges_path = 'data/processed/go_edges.json'
    
    if not os.path.exists(nodes_path):
        print(f'❌ {nodes_path} not found')
        sys.exit(1)
    if not os.path.exists(edges_path):
        print(f'❌ {edges_path} not found')
        sys.exit(1)
    
    with open(nodes_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)
    with open(edges_path, 'r', encoding='utf-8') as f:
        edges = json.load(f)
    
    print(f'✅ Loaded {len(nodes)} nodes, {len(edges)} edges\n')
    
    # Import nodes
    print('Importing nodes (BiologicalProcess)...')
    cy_nodes = """
    UNWIND $batch AS n
    MERGE (b:BiologicalProcess {id: n.id})
    SET b.label = n.label, b.namespace = n.namespace
    RETURN count(*) AS imported
    """
    
    batch_size = 100
    total_nodes_imported = 0
    try:
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i+batch_size]
            result = client.run_query(cy_nodes, {'batch': batch})
            count = result[0]['imported'] if result else 0
            total_nodes_imported += count
        print(f'✅ Nodes imported: {total_nodes_imported}\n')
    except Exception as e:
        print(f'❌ Error importing nodes: {e}')
        client.close()
        sys.exit(1)
    
    # Import edges
    print('Importing relationships...')
    
    is_a_edges = [e for e in edges if e.get('relation') == 'IS_A']
    part_of_edges = [e for e in edges if e.get('relation') == 'PART_OF']
    
    cy_is_a = """
    UNWIND $batch AS e
    MATCH (a {id: e.source})
    MATCH (b {id: e.target})
    MERGE (a)-[:IS_A]->(b)
    RETURN count(*) AS imported
    """
    
    cy_part_of = """
    UNWIND $batch AS e
    MATCH (a {id: e.source})
    MATCH (b {id: e.target})
    MERGE (a)-[:PART_OF]->(b)
    RETURN count(*) AS imported
    """
    
    total_is_a = 0
    total_part_of = 0
    
    try:
        # Import IS_A
        for i in range(0, len(is_a_edges), batch_size):
            batch = is_a_edges[i:i+batch_size]
            result = client.run_query(cy_is_a, {'batch': batch})
            count = result[0]['imported'] if result else 0
            total_is_a += count
        
        # Import PART_OF
        for i in range(0, len(part_of_edges), batch_size):
            batch = part_of_edges[i:i+batch_size]
            result = client.run_query(cy_part_of, {'batch': batch})
            count = result[0]['imported'] if result else 0
            total_part_of += count
        
        total_edges = total_is_a + total_part_of
        print(f'✅ Relationships imported: {total_edges} (IS_A: {total_is_a}, PART_OF: {total_part_of})\n')
    except Exception as e:
        print(f'❌ Error importing edges: {e}')
        client.close()
        sys.exit(1)
    
    # Display summary
    print('=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'Nodes imported: {total_nodes_imported}')
    print(f'Relationships imported: {total_edges}')
    
    # Validate
    print('\nValidation queries:')
    try:
        q_bp = 'MATCH (n:BiologicalProcess) RETURN count(n) AS count'
        r_bp = client.run_query(q_bp)
        bp_count = r_bp[0]['count'] if r_bp else 0
        print(f'  BiologicalProcess nodes: {bp_count}')
        
        q_is_a = 'MATCH ()-[r:IS_A]->() RETURN count(r) AS count'
        r_is_a = client.run_query(q_is_a)
        is_a_count = r_is_a[0]['count'] if r_is_a else 0
        print(f'  IS_A relationships: {is_a_count}')
        
        q_part_of = 'MATCH ()-[r:PART_OF]->() RETURN count(r) AS count'
        r_part_of = client.run_query(q_part_of)
        part_of_count = r_part_of[0]['count'] if r_part_of else 0
        print(f'  PART_OF relationships: {part_of_count}')
    except Exception as e:
        print(f'\n⚠️  Validation warning: {e}')
    
    client.close()
    print('\n✅ Import complete')


if __name__ == '__main__':
    main()
