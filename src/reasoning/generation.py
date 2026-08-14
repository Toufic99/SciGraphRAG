"""Génération de réponse à partir du contexte hybride graphe + texte.

Dernière brique du pipeline GraphRAG. Le modèle reçoit trois niveaux d'information
et doit rédiger une réponse *traçable* : chaque affirmation doit pouvoir être
rattachée soit à une relation du graphe, soit à un PMID précis.

Le point important n'est pas la qualité rédactionnelle mais la contrainte de
citation : sans elle, on retombe sur un RAG ordinaire dont on ne peut pas
vérifier les affirmations.
"""

from __future__ import annotations

import os

from reasoning.retrieval import Contexte

MODELE_DEFAUT = "claude-sonnet-4-5"

SYSTEME = """Tu es un assistant de recherche biomédicale adossé à un graphe de connaissances \
(Gene Ontology + Reactome) enrichi d'abstracts PubMed.

Règles impératives :
1. Ne réponds qu'à partir du contexte fourni. Si l'information manque, dis-le explicitement.
2. Cite tes sources en continu : [PMID xxxxx] pour un fait tiré d'une publication, \
et mentionne la relation ontologique quand tu t'appuies sur la structure du graphe \
(par exemple « X est un sous-type de Y (IS_A) »).
3. Distingue clairement ce qui vient du graphe (structure curatée) de ce qui vient \
des abstracts (littérature).
4. Termine par une section « Limites » signalant ce que le contexte ne permet pas d'affirmer.
5. Réponds en français, même si les sources sont en anglais."""

GABARIT = """Question : {question}

--- CONTEXTE ---
{contexte}
--- FIN DU CONTEXTE ---

Rédige une réponse structurée et sourcée."""


def construire_prompt(ctx: Contexte) -> str:
    """Assemble le prompt utilisateur à partir du contexte hybride."""
    return GABARIT.format(question=ctx.question, contexte=ctx.en_texte())


def generer(ctx: Contexte, modele: str = MODELE_DEFAUT) -> str:
    """Appelle le LLM. Nécessite ANTHROPIC_API_KEY dans l'environnement."""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError(
            "Le paquet 'anthropic' est absent. Installer avec : pip install anthropic\n"
            "Sans clé API, utiliser construire_prompt() pour inspecter le contexte."
        )

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY absente de l'environnement.\n"
            "Ajouter la clé dans .env, ou se contenter de construire_prompt()."
        )

    client = Anthropic()
    reponse = client.messages.create(
        model=modele,
        max_tokens=1500,
        system=SYSTEME,
        messages=[{"role": "user", "content": construire_prompt(ctx)}],
    )
    return "".join(bloc.text for bloc in reponse.content if bloc.type == "text")


def _demo() -> None:
    """Vérifie que le prompt contient bien les trois niveaux du contexte.

    Ne fait aucun appel réseau : on teste la construction, pas le modèle.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from dotenv import load_dotenv
    from kg.neo4j_client import Neo4jClient
    from reasoning.retrieval import recuperer_contexte

    load_dotenv()
    client = Neo4jClient()
    client.connect()

    ctx = recuperer_contexte(client, "DNA repair after alkylation damage", k=5)
    prompt = construire_prompt(ctx)

    assert "CONCEPTS DU GRAPHE" in prompt, "les concepts manquent dans le prompt"
    assert "PUBLICATIONS" in prompt, "les publications manquent dans le prompt"
    assert "PMID" in prompt, "aucune référence citable dans le prompt"

    print(f"OK — prompt de {len(prompt)} caractères")
    print(f"  {len(ctx.publications)} publications, {len(ctx.concepts)} concepts, "
          f"{len(ctx.relations)} relations")
    print("\n--- Aperçu du contexte transmis au modèle ---")
    apercu = ctx.en_texte(extrait=180)
    print(apercu[:1100] + ("\n[...]" if len(apercu) > 1100 else ""))
    client.close()


if __name__ == "__main__":
    _demo()
