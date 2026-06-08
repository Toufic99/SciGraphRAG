"""
mapper.py

Populate Neo4j from nodes/edges JSON produced by fetch_go.py.
Handles:
  - Node import (BiologicalProcess)
  - Edge import (IS_A, PART_OF)
  - Schema constraints
  - Validation queries
"""
import json
import argparse
import sys
from kg.neo4j_client import Neo4jClient
from kg.schema import apply_schema


def import_biologicalprocesses(client, nodes, batch_size=500):
    """Import nodes as BiologicalProcess labels."""
    if not nodes:
        print('No nodes to import')
        return 0
    
    cy = """
    UNWIND $batch AS n
    MERGE (b:BiologicalProcess {id: n.id})
    SET b.label = n.label, b.namespace = n.namespace
    RETURN count(*) AS imported
    """
    
    total = 0
    try:
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i+batch_size]
            result = client.run_query(cy, {'batch': batch})
            count = result[0]['imported'] if result else 0
            total += count
            print(f'  Batch {i//batch_size + 1}: {count} nodes')
    except Exception as e:
        print(f'Error importing nodes: {e}')
        return 0
    
    return total


def import_edges(client, edges, batch_size=500):
    """Import edges (IS_A, PART_OF) without APOC."""
    if not edges:
        print('No edges to import')
        return 0, 0, 0
    
    # Separate into IS_A and PART_OF for clarity
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
    
    is_a_count = 0
    part_of_count = 0
    
    # Import IS_A
    try:
        for i in range(0, len(is_a_edges), batch_size):
            batch = is_a_edges[i:i+batch_size]
            result = client.run_query(cy_is_a, {'batch': batch})
            count = result[0]['imported'] if result else 0
            is_a_count += count
            print(f'  IS_A Batch {i//batch_size + 1}: {count} edges')
    except Exception as e:
        print(f'Error importing IS_A edges: {e}')
    
    # Import PART_OF
    try:
        for i in range(0, len(part_of_edges), batch_size):
            batch = part_of_edges[i:i+batch_size]
            result = client.run_query(cy_part_of, {'batch': batch})
            count = result[0]['imported'] if result else 0
            part_of_count += count
            print(f'  PART_OF Batch {i//batch_size + 1}: {count} edges')
    except Exception as e:
        print(f'Error importing PART_OF edges: {e}')
    
    return is_a_count, part_of_count, len(edges)


def validate_import(client):
    """Run validation queries."""
    print('\n=== VALIDATION QUERIES ===')
    
    q1 = 'MATCH (n:BiologicalProcess) RETURN count(n) AS count'
    q2 = 'MATCH ()-[r:IS_A]->() RETURN count(r) AS count'
    q3 = 'MATCH ()-[r:PART_OF]->() RETURN count(r) AS count'
    
    try:
        r1 = client.run_query(q1)
        count_bp = r1[0]['count'] if r1 else 0
        print(f'BiologicalProcess nodes: {count_bp}')
        
        r2 = client.run_query(q2)
        count_is_a = r2[0]['count'] if r2 else 0
        print(f'IS_A relations: {count_is_a}')
        
        r3 = client.run_query(q3)
        count_part_of = r3[0]['count'] if r3 else 0
        print(f'PART_OF relations: {count_part_of}')
        
        return count_bp, count_is_a, count_part_of
    except Exception as e:
        print(f'Error during validation: {e}')
        return 0, 0, 0


def show_subgraph_example(client):
    """Show example subgraph around 'apoptotic process'."""
    print('\n=== SUBGRAPH EXAMPLE: apoptotic process ===')
    
    q = """
    MATCH (root:BiologicalProcess {label: 'apoptotic process'})
    CALL apoc.path.subgraphNodes(root, {relationshipFilter: 'IS_A|PART_OF', maxLevel: 2})
    YIELD node
    RETURN node.id AS id, node.label AS label
    LIMIT 15
    """
    
    # Fallback without APOC: simple BFS
    q_fallback = """
    MATCH (root:BiologicalProcess)
    WHERE TOLOWER(root.label) CONTAINS 'apoptotic process'
    WITH root
    OPTIONAL MATCH (root)-[r1:IS_A|PART_OF]->(n1)
    OPTIONAL MATCH (root)<-[r2:IS_A|PART_OF]-(n2)
    OPTIONAL MATCH (root)-[r3:IS_A|PART_OF]->(n3)-[r4:IS_A|PART_OF]->(n4)
    WITH root, n1, n2, n3, n4
    WHERE root IS NOT NULL
    RETURN root.id AS id, root.label AS label, 'root' AS type
    UNION
    MATCH (root:BiologicalProcess)
    WHERE TOLOWER(root.label) CONTAINS 'apoptotic process'
    WITH root
    OPTIONAL MATCH (root)-[r1:IS_A|PART_OF]->(n1)
    WHERE n1 IS NOT NULL
    RETURN n1.id AS id, n1.label AS label, 'child' AS type
    UNION
    MATCH (root:BiologicalProcess)
    WHERE TOLOWER(root.label) CONTAINS 'apoptotic process'
    WITH root
    OPTIONAL MATCH (root)-[r1:IS_A|PART_OF]->(n1)-[r2:IS_A|PART_OF]->(n2)
    WHERE n2 IS NOT NULL
    RETURN n2.id AS id, n2.label AS label, 'grandchild' AS type
    LIMIT 20
    """
    
    try:
        result = client.run_query(q_fallback)
        if result:
            print(f'Found {len(result)} nodes in subgraph:')
            for row in result:
                print(f'  - {row.get("label")} ({row.get("type")})')
        else:
            print('No subgraph found. Showing sample nodes:')
            q_sample = 'MATCH (n:BiologicalProcess) RETURN n.id, n.label LIMIT 5'
            sample = client.run_query(q_sample)
            for row in sample:
                print(f'  - {row.get("n.label")}')
    except Exception as e:
        print(f'Error during subgraph query: {e}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--nodes', help='nodes JSON file', required=True)
    parser.add_argument('--edges', help='edges JSON file', required=True)
    parser.add_argument('--apply-schema', action='store_true', help='Apply constraints and indexes')
    args = parser.parse_args()

    client = Neo4jClient()
    
    try:
        client.connect()
        print('Connected to Neo4j')
    except Exception as e:
        print(f'Failed to connect to Neo4j: {e}')
        print('Please ensure .env file has correct NEO4J_* variables')
        sys.exit(1)

    # Apply schema if requested
    if args.apply_schema:
        print('\nApplying schema constraints and indexes...')
        apply_schema(client)

    # Load JSON files
    print('\nLoading JSON files...')
    with open(args.nodes, 'r', encoding='utf-8') as f:
        nodes = json.load(f)
    with open(args.edges, 'r', encoding='utf-8') as f:
        edges = json.load(f)
    
    print(f'Loaded {len(nodes)} nodes, {len(edges)} edges')

    # Import
    print('\nImporting nodes...')
    node_count = import_biologicalprocesses(client, nodes)
    print(f'✅ Imported {node_count} nodes')
    
    print('\nImporting edges...')
    is_a_count, part_of_count, total_edge_count = import_edges(client, edges)
    print(f'✅ Imported {is_a_count} IS_A + {part_of_count} PART_OF = {is_a_count + part_of_count} total edges')

    # Validate
    count_bp, count_is_a, count_part_of = validate_import(client)
    
    # Show example
    show_subgraph_example(client)
    
    # Cleanup
    client.close()
    print('\n✅ Import and validation complete')


if __name__ == '__main__':
    main()
