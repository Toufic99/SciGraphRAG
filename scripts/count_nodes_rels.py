#!/usr/bin/env python3
"""
count_nodes_rels.py

Counts total nodes and total relationships in the connected Neo4j instance.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from kg.neo4j_client import Neo4jClient

client = Neo4jClient()
try:
    client.connect()
except Exception as e:
    print('Connection error:', e)
    sys.exit(1)

q1 = 'MATCH (n) RETURN count(n) AS c'
q2 = 'MATCH ()-[r]->() RETURN count(r) AS c'

try:
    r1 = client.run_query(q1)
    nodes = r1[0]['c'] if r1 else 0
    print('TOTAL_NODES:', nodes)

    r2 = client.run_query(q2)
    rels = r2[0]['c'] if r2 else 0
    print('TOTAL_RELATIONSHIPS:', rels)
except Exception as e:
    print('Query error:', e)
finally:
    client.close()
