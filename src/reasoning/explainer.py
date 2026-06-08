"""
explainer.py

Transform a Neo4j subgraph (nodes+edges) into a human-readable reasoning trace.
"""
import networkx as nx
import json


def explain(subgraph):
    """subgraph: dict with 'nodes' and 'edges' where nodes are dicts with id/label/type and edges with source/target/relation"""
    G = nx.DiGraph()
    id_to_label = {}
    for n in subgraph.get('nodes', []):
        nid = n.get('id') or n.get('uniprot') or n.get('name')
        label = n.get('label') or n.get('name') or n.get('uniprot')
        G.add_node(nid, **n)
        id_to_label[nid] = label
    for e in subgraph.get('edges', []):
        s = e.get('source')
        t = e.get('target')
        rel = e.get('relation')
        G.add_edge(s, t, relation=rel)

    # pick a root as a node containing 'apoptosis' or first node
    root = None
    for nid, data in G.nodes(data=True):
        lab = (data.get('label') or '').lower()
        if 'apoptosis' in lab:
            root = nid
            break
    if root is None:
        root = list(G.nodes())[0] if G.nodes() else None

    lines = []
    def dfs(u, depth=0, visited=set()):
        if u in visited:
            return
        visited.add(u)
        indent = '  ' * depth
        lines.append(f"{indent}- {id_to_label.get(u, u)} ({u})")
        for v in G.successors(u):
            rel = G[u][v].get('relation')
            lines.append(f"{indent}  └─ {rel} → {id_to_label.get(v, v)}")
            dfs(v, depth+2, visited)

    if root:
        dfs(root)
    return '\n'.join(lines)
