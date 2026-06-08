"""
fetch_go.py

Robust parser for Gene Ontology (go.owl) using rdflib.
Produces a filtered subset (keywords: apoptosis, metabolism, DNA repair)
and exports nodes/edges JSON ready for Neo4j import.

Usage:
    python src/ingest/fetch_go.py --input data/raw/go.owl --out data/processed/
"""

import argparse
import json
import os
import sys
import logging
from rdflib import Graph, RDFS, Namespace, URIRef

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

KEYWORDS = ["apoptosis", "metabolism", "dna repair"]
OBOINOWL = Namespace('http://www.geneontology.org/formats/oboInOwl#')
BFO_PART_OF = URIRef('http://purl.obolibrary.org/obo/BFO_0000050')


def parse_graph(input_path):
    g = Graph()
    logging.info('Parsing %s', input_path)
    try:
        g.parse(input_path)
    except Exception as e:
        logging.error('Failed to parse OWL: %s', e)
        raise
    return g


def count_triples(g):
    return len(g)


def sparql_examples(g):
    prefixes = '\n'.join([
        'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>',
        'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>',
        'PREFIX owl: <http://www.w3.org/2002/07/owl#>',
        'PREFIX oboInOwl: <http://www.geneontology.org/formats/oboInOwl#>',
        'PREFIX bfo: <http://purl.obolibrary.org/obo/BFO_>'
    ])

    q1 = prefixes + '\nSELECT ?term ?label WHERE { ?term a owl:Class . ?term rdfs:label ?label . } LIMIT 5'
    q2 = prefixes + '\nSELECT ?s ?o WHERE { ?s rdfs:subClassOf ?o } LIMIT 5'
    # Try to catch part_of via BFO_0000050 or predicates containing 'part'
    q3 = prefixes + '\nSELECT ?s ?p ?o WHERE { ?s ?p ?o . FILTER(CONTAINS(LCASE(STR(?p)), "part" ) || STR(?p) = "http://purl.obolibrary.org/obo/BFO_0000050") } LIMIT 5'

    out1 = list(g.query(q1))
    out2 = list(g.query(q2))
    out3 = list(g.query(q3))
    return out1, out2, out3


def extract_subset(g):
    # Get all classes with labels and namespace
    prefixes = '\n'.join([
        'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>',
        'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>',
        'PREFIX owl: <http://www.w3.org/2002/07/owl#>',
        'PREFIX oboInOwl: <http://www.geneontology.org/formats/oboInOwl#>'
    ])
    q = prefixes + '\nSELECT ?term ?label ?ns WHERE { ?term a owl:Class . ?term rdfs:label ?label . OPTIONAL { ?term oboInOwl:hasOBONamespace ?ns } }'
    res = g.query(q)

    nodes = {}
    for row in res:
        term = str(row.term)
        label = str(row.label)
        ns = str(row.ns) if hasattr(row, 'ns') and row.ns else ''
        nodes[term] = {'id': term, 'label': label, 'namespace': ns}

    logging.info('Total classes discovered: %d', len(nodes))

    # Collect direct subclass relations where target is a class URI.
    # Anonymous OWL restriction nodes are intentionally skipped here.
    edges = []
    for s, p, o in g.triples((None, RDFS.subClassOf, None)):
        if str(o) in nodes:
            edges.append({'source': str(s), 'relation': 'IS_A', 'target': str(o)})

    # GO encodes part_of mostly via OWL restrictions:
    # class rdfs:subClassOf [ a owl:Restriction ; owl:onProperty BFO_0000050 ; owl:someValuesFrom filler ]
    q_part_of_restrictions = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT ?cls ?filler WHERE {
      ?cls rdfs:subClassOf ?restriction .
      ?restriction a owl:Restriction ;
                   owl:onProperty <http://purl.obolibrary.org/obo/BFO_0000050> .
      {
        ?restriction owl:someValuesFrom ?filler .
      }
      UNION
      {
        ?restriction owl:allValuesFrom ?filler .
      }
    }
    """
    for row in g.query(q_part_of_restrictions):
        src = str(row.cls)
        tgt = str(row.filler)
        if src in nodes and tgt in nodes:
            edges.append({'source': src, 'relation': 'PART_OF', 'target': tgt})

    # De-duplicate edges while preserving order
    seen = set()
    dedup_edges = []
    for e in edges:
        key = (e['source'], e['relation'], e['target'])
        if key not in seen:
            seen.add(key)
            dedup_edges.append(e)
    edges = dedup_edges

    # Filter nodes by keywords in label (case-insensitive)
    matched = set()
    for nid, meta in nodes.items():
        lab = meta.get('label', '').lower()
        if any(k in lab for k in KEYWORDS):
            matched.add(nid)

    logging.info('Nodes matching keywords: %d', len(matched))

    # Add direct parents via IS_A relations (if object is a URI in nodes)
    to_include = set(matched)
    for e in edges:
        if e['relation'] in ('IS_A', 'PART_OF'):
            if e['source'] in matched and e['target'] in nodes:
                to_include.add(e['target'])
            if e['target'] in matched and e['source'] in nodes:
                to_include.add(e['source'])

    final_nodes = [nodes[n] for n in to_include if n in nodes]
    final_edges = [e for e in edges if e['source'] in to_include and e['target'] in to_include]

    return final_nodes, final_edges


def save_json(nodes, edges, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    nodes_out = os.path.join(out_dir, 'go_nodes.json')
    edges_out = os.path.join(out_dir, 'go_edges.json')
    with open(nodes_out, 'w', encoding='utf-8') as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
    with open(edges_out, 'w', encoding='utf-8') as f:
        json.dump(edges, f, ensure_ascii=False, indent=2)
    return nodes_out, edges_out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='Path to go.owl')
    parser.add_argument('--out', required=True, help='Output directory for processed JSON')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        logging.error('Input file not found: %s', args.input)
        sys.exit(1)

    g = parse_graph(args.input)
    tcount = count_triples(g)
    logging.info('Total RDF triples: %d', tcount)

    # SPARQL exploration
    out1, out2, out3 = sparql_examples(g)
    logging.info('SPARQL example results: classes=%d, subclass=%d, part_of=%d', len(out1), len(out2), len(out3))

    # print 5 results each
    print('\n-- Sample OWL Classes (5) --')
    for r in out1[:5]:
        print(str(r[0]), '-', str(r[1]))
    print('\n-- Sample rdfs:subClassOf (5) --')
    for r in out2[:5]:
        print(str(r[0]), 'subClassOf', str(r[1]))
    print('\n-- Sample part_of-like predicates (5) --')
    for r in out3[:5]:
        print(str(r[0]), str(r[1]), str(r[2]))

    # Extraction
    nodes, edges = extract_subset(g)

    nodes_out, edges_out = save_json(nodes, edges, args.out)

    # Validation prints
    print('\n✅ Nodes extracted:', len(nodes))
    print('✅ Edges extracted:', len(edges))
    print('✅ go_nodes.json saved')
    print('✅ go_edges.json saved')

    print('\nSample nodes (5):')
    for n in nodes[:5]:
        print(n)
    print('\nSample edges (5):')
    for e in edges[:5]:
        print(e)


if __name__ == '__main__':
    main()
