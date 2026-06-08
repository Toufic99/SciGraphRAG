"""
subgraph_vis.py

Visualize a subgraph (nodes+edges) using pyvis and export an HTML file.
"""
from pyvis.network import Network

COLOR_MAP = {
    'BiologicalProcess': '#4A90D9',
    'Pathway': '#27AE60',
    'Protein': '#E67E22'
}


def visualize(subgraph, output_path, title='Subgraph'):
    net = Network(height='600px', width='100%', bgcolor='#ffffff')
    net.toggle_physics(True)

    for n in subgraph.get('nodes', []):
        nid = n.get('id') or n.get('uniprot') or n.get('name')
        ntype = n.get('type') or n.get('label') or ''
        color = COLOR_MAP.get(ntype, '#95A5A6')
        title_txt = '<br>'.join([f"{k}: {v}" for k, v in n.items()])
        net.add_node(nid, label=str(n.get('label') or n.get('name') or nid), title=title_txt, color=color)

    for e in subgraph.get('edges', []):
        s = e.get('source')
        t = e.get('target')
        label = e.get('relation')
        net.add_edge(s, t, title=label, label=label)

    net.show_buttons(filter_=['physics'])
    net.show(output_path)
    return output_path
