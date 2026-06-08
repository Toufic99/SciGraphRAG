#!/usr/bin/env python3
"""
show_go_graph.py

Affiche un résumé du graphe GO dans Neo4j: compte, 10 nœuds d'exemple,
10 relations d'exemple, et le sous-graphe autour de "apoptotic process".

Usage:
  python scripts/show_go_graph.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from kg.neo4j_client import Neo4jClient

client = Neo4jClient()
try:
    client.connect()
except Exception as e:
    print('Erreur de connexion:', e)
    sys.exit(1)

print('\n=== GO Graph Overview ===')
q_counts = {
    'BiologicalProcess': 'MATCH (n:BiologicalProcess) RETURN count(n) AS c',
    'IS_A': 'MATCH ()-[r:IS_A]->() RETURN count(r) AS c',
    'PART_OF': 'MATCH ()-[r:PART_OF]->() RETURN count(r) AS c'
}
for k,q in q_counts.items():
    res = client.run_query(q)
    val = res[0]['c'] if res else 0
    print(f'{k}: {val}')

print('\n=== 10 sample BiologicalProcess nodes ===')
q_sample_nodes = 'MATCH (n:BiologicalProcess) RETURN n.id AS id, n.label AS label LIMIT 10'
res = client.run_query(q_sample_nodes)
for r in res:
    print('-', r.get('label'), '|', r.get('id'))

print('\n=== 10 sample relationships (type, source_label -> target_label) ===')
q_sample_rel = '''
MATCH (a:BiologicalProcess)-[r]->(b:BiologicalProcess)
RETURN TYPE(r) AS rel, a.label AS a_label, b.label AS b_label
LIMIT 10
'''
res = client.run_query(q_sample_rel)
for r in res:
    print('-', r.get('rel'), ':', r.get('a_label'), '->', r.get('b_label'))

print('\n=== Subgraph around "apoptotic process" (root + direct neighbors) ===')
q_sub = '''
MATCH (root:BiologicalProcess)
WHERE TOLOWER(root.label) CONTAINS 'apoptotic'
OPTIONAL MATCH (root)-[r:IS_A|PART_OF]-(n)
RETURN root.label AS root_label, COLLECT(DISTINCT {rel:TYPE(r), label: n.label}) AS neighbors
LIMIT 1
'''
res = client.run_query(q_sub)
if res:
    row = res[0]
    print('Root:', row.get('root_label'))
    neighbors = row.get('neighbors') or []
    if neighbors:
        for nb in neighbors[:20]:
            print('-', nb.get('rel'), nb.get('label'))
    else:
        print('No neighbors found')
else:
    print('No apoptotic root found')

client.close()
print('\n=== Done ===')
