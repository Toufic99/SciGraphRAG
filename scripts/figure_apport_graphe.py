#!/usr/bin/env python3
"""
scripts/figure_apport_graphe.py

Produit la figure du README : pour une question donnée, distingue visuellement
les concepts remontés par la recherche vectorielle (via les abstracts) de ceux
qui n'apparaissent que par la traversée de l'ontologie.

C'est la mesure de ce qu'un RAG classique ne peut pas produire, rendue lisible.

Usage:
    PYTHONPATH=src python scripts/figure_apport_graphe.py
    PYTHONPATH=src python scripts/figure_apport_graphe.py --question "apoptosis" --sortie docs/images/x.png
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import matplotlib
matplotlib.use("Agg")

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
from dotenv import load_dotenv

from kg.neo4j_client import Neo4jClient
from reasoning.retrieval import recuperer_contexte

FOND = "#fafaf8"
DEPUIS_TEXTE = "#0d7a5f"      # vert : concept cité par un abstract retrouvé
DEPUIS_TEXTE_FOND = "#e7f4ef"
DEPUIS_GRAPHE = "#6446ad"     # violet : concept apporté par l'ontologie seule
DEPUIS_GRAPHE_FOND = "#f1ecfb"
TRAIT = "#b9bdb8"


def profondeur(G, noeud, cache=None):
    """Distance au plus lointain ancêtre, pour empiler les niveaux IS_A."""
    cache = cache if cache is not None else {}
    if noeud in cache:
        return cache[noeud]
    cache[noeud] = 0  # coupe les cycles éventuels
    parents = list(G.successors(noeud))
    cache[noeud] = 1 + max((profondeur(G, p, cache) for p in parents), default=-1)
    return cache[noeud]


# Unités de la figure = pouces, pour que l'espacement se calcule directement
# sur la largeur du texte et que deux libellés longs ne se chevauchent jamais.
LARGEUR_CAR = 0.078      # largeur moyenne d'un caractère à 10 pt, en pouces
MARGE_BOITE = 0.34       # padding de la boîte arrondie
ECART = 0.5              # espace minimal entre deux boîtes voisines
HAUTEUR_NIVEAU = 1.55


def largeur_boite(libelle):
    return len(libelle) * LARGEUR_CAR + MARGE_BOITE * 2


def disposer(G):
    """Layout en couches : les parents ontologiques au-dessus de leurs enfants.

    `profondeur` compte les ancêtres, donc un concept général vaut 0. On inverse
    le signe pour que le général se retrouve en haut, sens de lecture d'un IS_A.
    Chaque niveau est réparti selon la largeur réelle des libellés.
    """
    niveaux = {n: profondeur(G, n) for n in G.nodes}
    par_niveau = {}
    for n, k in niveaux.items():
        par_niveau.setdefault(k, []).append(n)

    pos = {}
    for k, noeuds in par_niveau.items():
        noeuds.sort()
        largeurs = [largeur_boite(n) for n in noeuds]
        total = sum(largeurs) + ECART * (len(noeuds) - 1)
        curseur = -total / 2
        for n, w in zip(noeuds, largeurs):
            pos[n] = (curseur + w / 2, -float(k) * HAUTEUR_NIVEAU)
            curseur += w + ECART
    return pos


def construire(ctx):
    G = nx.DiGraph()
    hors_texte = ctx.concepts_du_graphe_seul()

    for r in ctx.relations:
        if r.sens == "composition":
            continue  # la source est un résumé de protéines, pas un concept
        G.add_edge(r.source, r.cible, type=r.type)

    for n in G.nodes:
        G.nodes[n]["depuis_graphe"] = n in hors_texte
    return G, hors_texte


def _par_niveau(pos):
    d = {}
    for n, (_, y) in pos.items():
        d.setdefault(y, []).append(n)
    return d


def tracer(G, hors_texte, question, sortie):
    pos = disposer(G)
    niveaux = _par_niveau(pos)

    # 1 unité de données = 1 pouce : la figure épouse exactement le layout.
    xs = [x for x, _ in pos.values()]
    span_x = (max(xs) + max(largeur_boite(n) for n in G.nodes) / 2) - \
             (min(xs) - max(largeur_boite(n) for n in G.nodes) / 2)
    largeur = max(9.0, span_x)
    hauteur = max(4.0, HAUTEUR_NIVEAU * len(niveaux) + 1.8)

    fig, ax = plt.subplots(figsize=(largeur, hauteur), facecolor=FOND)
    ax.set_facecolor(FOND)

    # Flèches d'abord, pour qu'elles passent sous les boîtes.
    for source, cible, d in G.edges(data=True):
        x1, y1 = pos[source]
        x2, y2 = pos[cible]
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops={"arrowstyle": "-|>", "color": TRAIT, "linewidth": 1.5,
                        "shrinkA": 22, "shrinkB": 22,
                        "connectionstyle": "arc3,rad=0.04"},
        )
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, d["type"],
                ha="center", va="center", fontsize=7.5, family="monospace",
                color="#8a9096",
                bbox={"facecolor": FOND, "edgecolor": "none", "pad": 1.5})

    for n, (x, y) in pos.items():
        graphe = G.nodes[n]["depuis_graphe"]
        ax.text(
            x, y, n, ha="center", va="center", fontsize=10,
            color=DEPUIS_GRAPHE if graphe else DEPUIS_TEXTE,
            fontweight="bold" if graphe else "normal",
            bbox={
                "boxstyle": "round,pad=0.45",
                "facecolor": DEPUIS_GRAPHE_FOND if graphe else DEPUIS_TEXTE_FOND,
                "edgecolor": DEPUIS_GRAPHE if graphe else DEPUIS_TEXTE,
                "linewidth": 1.1,
            },
        )

    ax.set_title(
        f"« {question} »\n"
        f"{len(hors_texte)} des {G.number_of_nodes()} concepts ne figurent dans aucun résumé retrouvé",
        fontsize=13, color="#17191b", pad=20, loc="left",
    )
    ax.legend(
        handles=[
            mpatches.Patch(facecolor=DEPUIS_TEXTE_FOND, edgecolor=DEPUIS_TEXTE,
                           label="cité par un abstract retrouvé"),
            mpatches.Patch(facecolor=DEPUIS_GRAPHE_FOND, edgecolor=DEPUIS_GRAPHE,
                           label="apporté par la seule traversée de l'ontologie"),
        ],
        loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2,
        frameon=False, fontsize=10,
    )
    demi = max(largeur_boite(n) for n in G.nodes) / 2
    ax.set_xlim(min(xs) - demi, max(xs) + demi)
    ax.set_ylim(min(y for _, y in pos.values()) - 0.55,
                max(y for _, y in pos.values()) + 0.55)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(sortie, dpi=200, facecolor=FOND, bbox_inches="tight")
    print(f"Figure écrite : {sortie}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="DNA repair after alkylation damage")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--sortie", default="docs/images/apport-du-graphe.png")
    args = parser.parse_args()

    load_dotenv()
    client = Neo4jClient()
    client.connect()
    ctx = recuperer_contexte(client, args.question, k=args.k)
    client.close()

    if not ctx.relations:
        print("Aucune relation ontologique pour cette question — rien à tracer.")
        sys.exit(1)

    G, hors_texte = construire(ctx)
    tracer(G, hors_texte, args.question, args.sortie)


if __name__ == "__main__":
    main()
