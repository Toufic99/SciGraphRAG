"""
sparql_queries.py

SPARQL helper queries executed over an rdflib.Graph for exploration prior to Neo4j import.
"""
from rdflib import Namespace, RDFS

BP = Namespace('http://www.biopax.org/release/biopax-level3.owl#')


def get_processes_related_to_apoptosis(graph):
    q = """
    SELECT ?term ?label WHERE {
      ?term rdfs:label ?label .
      FILTER(CONTAINS(LCASE(STR(?label)), "apoptosis"))
    }
    """
    res = graph.query(q)
    out = []
    for row in res:
        out.append({"term": str(row.term), "label": str(row.label)})
    return out


def get_pathways_xenobiotic(graph):
    q = """
    SELECT ?pathway ?name WHERE {
      ?pathway rdf:type <http://www.biopax.org/release/biopax-level3.owl#Pathway> .
      ?pathway <http://www.biopax.org/release/biopax-level3.owl#displayName> ?name .
      FILTER(CONTAINS(LCASE(STR(?name)), "xenobiotic"))
    }
    """
    res = graph.query(q)
    out = []
    for row in res:
        out.append({"pathway": str(row.pathway), "name": str(row.name)})
    return out


def get_proteins_in_apoptosis(graph):
    q = """
    SELECT ?protein ?name ?pathway WHERE {
      ?protein rdf:type <http://www.biopax.org/release/biopax-level3.owl#Protein> .
      ?protein <http://www.biopax.org/release/biopax-level3.owl#displayName> ?name .
      ?pathway <http://www.biopax.org/release/biopax-level3.owl#participant> ?protein .
    }
    """
    res = graph.query(q)
    out = []
    for row in res:
        out.append({"protein": str(row.protein), "name": str(row.name), "pathway": str(row.pathway)})
    return out
