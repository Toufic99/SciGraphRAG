"""Démonstration web du pipeline GraphRAG.

Sert une page unique où l'on pose une question en langage naturel et où l'on voit
les trois niveaux de la réponse : les concepts du graphe, les chemins ontologiques
qui les relient, et les publications qui les documentent.

L'intérêt de la démo n'est pas la réponse rédigée — c'est de rendre visible
*sur quoi* elle s'appuie.

Lancement :
    PYTHONPATH=src uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from kg.neo4j_client import Neo4jClient           # noqa: E402
from reasoning.retrieval import recuperer_contexte  # noqa: E402

load_dotenv(RACINE / ".env")

app = FastAPI(title="SciGraphRAG", description="GraphRAG biomédical explicable")

# Polices servies localement plutôt que depuis un CDN : le pipeline entier
# fonctionne sans service externe, la démo aussi. Si le dossier est absent, la
# page reste fonctionnelle — les @font-face retombent sur les polices système.
_STATIQUE = Path(__file__).parent / "static"
if _STATIQUE.is_dir():
    app.mount("/static", StaticFiles(directory=_STATIQUE), name="static")

# Un seul client réutilisé : ouvrir une connexion Neo4j par requête est coûteux.
_client: Neo4jClient | None = None


def client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
        _client.connect()
    return _client


class Question(BaseModel):
    texte: str
    k: int = Field(default=5, ge=1, le=50)
    generer_reponse: bool = False


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


@app.get("/api/stats")
def stats() -> dict:
    """Chiffres du graphe, affichés en en-tête de la démo."""
    requete = """
    MATCH (b:BiologicalProcess) WITH count(b) AS processus
    MATCH (p:Pathway)           WITH processus, count(p) AS pathways
    MATCH (pr:Protein)          WITH processus, pathways, count(pr) AS proteines
    MATCH (pub:Publication)     WITH processus, pathways, proteines, count(pub) AS publications
    MATCH ()-[m:MENTIONS]->()
    RETURN processus, pathways, proteines, publications, count(m) AS mentions
    """
    r = client().run_query(requete)
    return dict(r[0]) if r else {}


@app.post("/api/question")
def poser(q: Question) -> dict:
    """Retrieval hybride, et génération LLM seulement si une clé est configurée."""
    ctx = recuperer_contexte(client(), q.texte, k=q.k)

    reponse = None
    erreur_generation = None
    if q.generer_reponse:
        if not os.getenv("ANTHROPIC_API_KEY"):
            erreur_generation = "ANTHROPIC_API_KEY absente — contexte affiché sans rédaction."
        else:
            try:
                from reasoning.generation import generer
                reponse = generer(ctx)
            except Exception as e:
                erreur_generation = f"{type(e).__name__}: {e}"

    apport_graphe = ctx.concepts_du_graphe_seul()

    return {
        "question": ctx.question,
        "pertinent": ctx.pertinent,
        "concepts": [
            {"nom": c.nom, "type": c.type, "publications": c.nb_publications}
            for c in ctx.concepts
        ],
        "relations": [
            {"source": r.source, "type": r.type, "cible": r.cible, "sens": r.sens}
            for r in ctx.relations
        ],
        # Ce que la traversée du graphe ajoute par rapport aux seuls abstracts.
        "apport_graphe": {
            "concepts_du_graphe": len(apport_graphe),
            "concepts_total": len(apport_graphe) + len(ctx.concepts),
        },
        "publications": [
            {
                "pmid": p.pmid,
                "titre": p.titre,
                "annee": p.annee,
                "journal": p.journal,
                "score": round(p.score, 3),
                "extrait": p.abstract[:400],
            }
            for p in ctx.publications
        ],
        "reponse": reponse,
        "erreur_generation": erreur_generation,
    }


@app.on_event("shutdown")
def fermer() -> None:
    if _client is not None:
        _client.close()
