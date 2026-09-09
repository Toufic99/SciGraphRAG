#!/usr/bin/env python3
"""
scripts/import_pubmed.py

Ajoute la couche textuelle du pipeline GraphRAG :
  1. Lit les concepts déjà présents dans le graphe (BiologicalProcess, Pathway)
  2. Interroge PubMed pour chacun
  3. Crée les noeuds :Publication et les relations (:Publication)-[:MENTIONS]->(concept)

Usage:
    python scripts/import_pubmed.py --tester            # 3 concepts, 3 publications
    python scripts/import_pubmed.py --concepts 30 --pubs 10
    python scripts/import_pubmed.py                     # tout le graphe

Prérequis:
    - .env avec NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    - graphe GO/Reactome déjà importé
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv

from ingest.pubmed import collecter_pour_concept
from kg.neo4j_client import Neo4jClient
from kg.schema import CONSTRAINTS, INDEXES

# Les concepts du graphe qu'on relie à la littérature.
# On lit le label pour GO, le nom pour Reactome — cohérent avec import_go/import_reactome.
REQUETE_CONCEPTS = """
MATCH (b:BiologicalProcess)
WHERE b.label IS NOT NULL
RETURN b.label AS terme, 'BiologicalProcess' AS type, b.id AS id
UNION
MATCH (p:Pathway)
WHERE p.name IS NOT NULL
RETURN p.name AS terme, 'Pathway' AS type, p.id AS id
"""

# MERGE sur le pmid : une publication citée par plusieurs concepts n'est stockée qu'une fois.
CYPHER_PUBLICATIONS = """
UNWIND $batch AS row
MERGE (pub:Publication {pmid: row.pmid})
  ON CREATE SET pub.title = row.title,
                pub.abstract = row.abstract,
                pub.year = row.year,
                pub.journal = row.journal
"""

CYPHER_LIENS_GO = """
UNWIND $batch AS row
MATCH (pub:Publication {pmid: row.pmid})
MATCH (c:BiologicalProcess {id: row.concept_id})
MERGE (pub)-[:MENTIONS]->(c)
"""

CYPHER_LIENS_PATHWAY = """
UNWIND $batch AS row
MATCH (pub:Publication {pmid: row.pmid})
MATCH (c:Pathway {id: row.concept_id})
MERGE (pub)-[:MENTIONS]->(c)
"""


def appliquer_schema(client):
    for q in CONSTRAINTS + INDEXES:
        client.run_query(q)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tester", action="store_true",
                        help="Mode test : 3 concepts, 3 publications chacun")
    parser.add_argument("--concepts", type=int, default=None,
                        help="Nombre de concepts à traiter (défaut : tous)")
    parser.add_argument("--pubs", type=int, default=10,
                        help="Publications par concept (défaut : 10)")
    args = parser.parse_args()

    if args.tester:
        args.concepts, args.pubs = 3, 3

    load_dotenv()
    client = Neo4jClient()

    print("=" * 62)
    print("Import PubMed — couche textuelle du GraphRAG")
    print("=" * 62)

    try:
        client.connect()
        client.run_query("RETURN 1")
    except Exception as e:
        print(f"Connexion Neo4j impossible : {e}")
        print("Vérifiez NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD dans .env")
        sys.exit(1)
    print("Connecté à Neo4j")

    appliquer_schema(client)

    concepts = [dict(r) for r in client.run_query(REQUETE_CONCEPTS)]
    if not concepts:
        print("Aucun concept dans le graphe — importez GO/Reactome d'abord.")
        sys.exit(1)

    if args.concepts is not None:
        concepts = concepts[:args.concepts]

    duree = len(concepts) * 2 * 0.4 / 60
    print(f"{len(concepts)} concepts à traiter, {args.pubs} publications chacun")
    print(f"Durée minimale estimée : ~{duree:.0f} min (étiquette NCBI 3 req/s)\n")

    total_pubs = 0
    total_liens = 0
    sans_resultat = 0

    for i, c in enumerate(concepts, 1):
        pubs = collecter_pour_concept(c["terme"], limite=args.pubs)
        if not pubs:
            sans_resultat += 1
            continue

        noeuds = [{
            "pmid": p.pmid, "title": p.titre, "abstract": p.abstract,
            "year": p.annee, "journal": p.journal,
        } for p in pubs]
        liens = [{"pmid": p.pmid, "concept_id": c["id"]} for p in pubs]

        client.batch_import(CYPHER_PUBLICATIONS, noeuds)
        cypher_lien = (CYPHER_LIENS_GO if c["type"] == "BiologicalProcess"
                       else CYPHER_LIENS_PATHWAY)
        client.batch_import(cypher_lien, liens)

        total_pubs += len(noeuds)
        total_liens += len(liens)

        if i % 10 == 0 or i == len(concepts):
            print(f"  {i}/{len(concepts)} concepts | {total_pubs} publications | {total_liens} liens")

    print(f"\n{'-' * 62}")
    print(f"Publications traitées : {total_pubs} (doublons fusionnés par pmid)")
    print(f"Liens MENTIONS        : {total_liens}")
    print(f"Concepts sans résultat: {sans_resultat}")

    stats = client.run_query("""
        RETURN COUNT { (pub:Publication) } AS pubs,
               COUNT { ()-[m:MENTIONS]->() } AS mentions
    """)
    if stats:
        r = stats[0]
        print(f"\nDans le graphe : {r['pubs']} Publication, {r['mentions']} MENTIONS")

    client.close()


if __name__ == "__main__":
    main()
