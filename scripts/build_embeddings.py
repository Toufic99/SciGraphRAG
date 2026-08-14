#!/usr/bin/env python3
"""
scripts/build_embeddings.py

Troisième étape du pipeline GraphRAG : vectorise les abstracts et crée
l'index vectoriel natif Neo4j.

  1. Crée l'index vectoriel (idempotent)
  2. Récupère les publications sans embedding
  3. Les encode en local (sentence-transformers, CPU)
  4. Stocke les vecteurs sur les noeuds :Publication
  5. Teste la recherche sémantique sur une question d'exemple

Usage:
    python scripts/build_embeddings.py
    python scripts/build_embeddings.py --question "DNA repair after alkylation"

Relançable : seules les publications non encodées sont traitées.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv

from kg.embeddings import (
    CREER_INDEX,
    DIMENSIONS,
    EFFACER_VECTEURS,
    ENREGISTRER_VECTEURS,
    MODELE_DEFAUT,
    PUBLICATIONS_SANS_VECTEUR,
    RECHERCHE_VECTORIELLE,
    SUPPRIMER_INDEX,
    encoder,
    encoder_question,
    resultats_pertinents,
)
from kg.neo4j_client import Neo4jClient

LOT = 16   # aligné sur le batch_size du modèle (e5-large est lourd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="DNA repair after alkylation damage",
                        help="Question de test pour la recherche sémantique")
    parser.add_argument("--k", type=int, default=5, help="Nombre de résultats")
    parser.add_argument("--reinitialiser", action="store_true",
                        help="Efface les vecteurs et l'index — obligatoire après "
                             "un changement de modèle (la dimension change)")
    args = parser.parse_args()

    load_dotenv()
    client = Neo4jClient()

    print("=" * 62)
    print("Embeddings + index vectoriel — étape 3 du GraphRAG")
    print("=" * 62)

    try:
        client.connect()
        client.run_query("RETURN 1")
    except Exception as e:
        print(f"Connexion Neo4j impossible : {e}")
        sys.exit(1)
    print("Connecté à Neo4j")

    if args.reinitialiser:
        client.run_query(SUPPRIMER_INDEX)
        client.run_query(EFFACER_VECTEURS)
        print("Vecteurs et index effacés (changement de modèle)")

    client.run_query(CREER_INDEX)
    print(f"Index vectoriel prêt ({DIMENSIONS} dimensions, cosinus)")

    lignes = [dict(r) for r in client.run_query(PUBLICATIONS_SANS_VECTEUR)]
    if not lignes:
        print("Toutes les publications sont déjà encodées.")
    else:
        print(f"{len(lignes)} publications à encoder (modèle : {MODELE_DEFAUT})\n")
        traitees = 0
        for i in range(0, len(lignes), LOT):
            paquet = lignes[i:i + LOT]
            textes = [f"{r['titre']}\n\n{r['abstract']}".strip() for r in paquet]
            vecteurs = encoder(textes)
            client.batch_import(ENREGISTRER_VECTEURS, [
                {"pmid": r["pmid"], "embedding": v}
                for r, v in zip(paquet, vecteurs)
            ])
            traitees += len(paquet)
            print(f"  {traitees}/{len(lignes)} encodées")

    # Vérification : la recherche sémantique doit renvoyer des résultats pertinents
    print(f"\n{'-' * 62}")
    print(f"Test de recherche : \"{args.question}\"\n")
    vecteur = encoder_question(args.question)
    resultats = client.run_query(RECHERCHE_VECTORIELLE, {"k": args.k, "vecteur": vecteur})

    if not resultats:
        print("Aucun résultat — vérifiez que des publications sont encodées.")
    elif not resultats_pertinents([r["score"] for r in resultats]):
        print("  (scores plats : le corpus ne semble pas contenir de réponse)\n")

    for r in resultats:
        print(f"  [{r['score']:.3f}] PMID {r['pmid']} ({r['annee']})")
        print(f"          {(r['titre'] or '')[:72]}")
        print(f"          concepts : {', '.join(r['concepts'][:3])}")
        print()

    total = client.run_query(
        "MATCH (p:Publication) WHERE p.embedding IS NOT NULL RETURN count(p) AS n"
    )
    print(f"Publications vectorisées dans le graphe : {total[0]['n']}")
    client.close()


if __name__ == "__main__":
    main()
