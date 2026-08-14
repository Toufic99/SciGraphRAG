"""Couche vectorielle du pipeline GraphRAG.

Encode les abstracts PubMed et les stocke sur les noeuds :Publication, avec un
index vectoriel natif Neo4j (5.13+). Pas de base vectorielle séparée : graphe et
vecteurs au même endroit, ce qui permet de croiser filtrage structurel (Cypher)
et similarité sémantique dans une seule requête.

Modèle : multilingual-e5-large.
Choisi après mesure : all-MiniLM-L6-v2 était nettement meilleur en anglais mais
traitait le français comme du bruit (0.184 sur une question pertinente, contre
0.795 pour la même question en anglais). Inacceptable pour un projet francophone.

Contrepartie : e5 tasse les scores dans une bande étroite. Sur trois passages
isolés, cette bande semble trop resserrée pour qu'un seuil absolu fonctionne —
c'est la conclusion qu'on en avait tirée, et elle était fausse. Mesurée sur les
428 publications du corpus, la bande reste étroite mais elle est *nette* :
questions couvertes >= 0.918, questions hors sujet <= 0.888.

Voir `resultats_pertinents()` et tests/test_pertinence.py pour la calibration.
"""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

MODELE_DEFAUT = "intfloat/multilingual-e5-large"
DIMENSIONS = 1024

# Les modèles E5 exigent ces préfixes : sans eux, la qualité chute nettement.
PREFIXE_QUESTION = "query: "
PREFIXE_DOCUMENT = "passage: "

# ponytail: e5-large pèse ~2.2 Go, ce qui alourdit le clonage du dépôt.
# intfloat/multilingual-e5-base (768 dim) ou -small (384 dim) sont 3 à 5 fois
# plus légers pour une qualité proche — penser à ajuster DIMENSIONS et à
# recréer l'index vectoriel si on change.

NOM_INDEX = "publication_embeddings"

# Un changement de modèle change la dimension : l'ancien index doit disparaître.
SUPPRIMER_INDEX = f"DROP INDEX {NOM_INDEX} IF EXISTS"

CREER_INDEX = f"""
CREATE VECTOR INDEX {NOM_INDEX} IF NOT EXISTS
FOR (p:Publication) ON (p.embedding)
OPTIONS {{indexConfig: {{
  `vector.dimensions`: {DIMENSIONS},
  `vector.similarity_function`: 'cosine'
}}}}
"""

PUBLICATIONS_SANS_VECTEUR = """
MATCH (p:Publication)
WHERE p.embedding IS NULL AND p.abstract IS NOT NULL
RETURN p.pmid AS pmid, p.title AS titre, p.abstract AS abstract
"""

EFFACER_VECTEURS = "MATCH (p:Publication) REMOVE p.embedding"

ENREGISTRER_VECTEURS = """
UNWIND $batch AS row
MATCH (p:Publication {pmid: row.pmid})
CALL db.create.setNodeVectorProperty(p, 'embedding', row.embedding)
"""

RECHERCHE_VECTORIELLE = f"""
CALL db.index.vector.queryNodes('{NOM_INDEX}', $k, $vecteur)
YIELD node AS pub, score
MATCH (pub)-[:MENTIONS]->(c)
RETURN pub.pmid AS pmid, pub.title AS titre, pub.year AS annee,
       left(pub.abstract, 400) AS extrait, score,
       collect(DISTINCT coalesce(c.label, c.name)) AS concepts
ORDER BY score DESC
"""

# Score minimal du meilleur résultat pour considérer que le corpus couvre la
# question. Mesuré sur les 428 publications (18 questions, cf.
# tests/test_pertinence.py) : couvertes >= 0.918, hors sujet <= 0.888.
# 0.90 se place entre les deux, à ~0.012 de chaque population.
#
# ponytail: valeur liée au corpus ET au modèle. Après un réimport PubMed
# élargi ou un changement d'embedding, remesurer — test_la_separation_reste_franche
# signale la dérive mais ne recalibre pas tout seul.
SEUIL_PERTINENCE = 0.90

_modele: SentenceTransformer | None = None


def charger_modele(nom: str = MODELE_DEFAUT) -> SentenceTransformer:
    """Charge le modèle une seule fois par processus (il pèse et met du temps)."""
    global _modele
    if _modele is None:
        _modele = SentenceTransformer(nom)
    return _modele


def _encoder(textes: list[str], nom_modele: str) -> list[list[float]]:
    modele = charger_modele(nom_modele)
    vecteurs = modele.encode(
        textes,
        batch_size=16,               # e5-large est plus lourd que MiniLM
        show_progress_bar=False,
        normalize_embeddings=True,   # requis pour la similarité cosinus
    )
    return [v.tolist() for v in vecteurs]


def encoder(textes: list[str], nom_modele: str = MODELE_DEFAUT) -> list[list[float]]:
    """Encode des documents (abstracts) avec le préfixe E5 attendu."""
    return _encoder([PREFIXE_DOCUMENT + t for t in textes], nom_modele)


def encoder_question(question: str, nom_modele: str = MODELE_DEFAUT) -> list[float]:
    """Encode une question avec le préfixe E5 attendu."""
    return _encoder([PREFIXE_QUESTION + question], nom_modele)[0]


def resultats_pertinents(scores: list[float], seuil: float = SEUIL_PERTINENCE) -> bool:
    """Le corpus contient-il vraiment une réponse, ou rend-il du bruit ?

    On tranche sur le niveau du meilleur score, pas sur sa distance à la moyenne.
    Cette distance ne porte aucune information ici : l'index vectoriel renvoie
    les k voisins les plus proches, qui se ressemblent donc entre eux quelle que
    soit la question. Mesurée sur le corpus, elle vaut ~0.005 aussi bien pour
    « apoptosis regulation » que pour « recette de pizza » — les deux populations
    se chevauchent et aucun seuil d'écart ne les sépare.

    Le niveau absolu, lui, sépare franchement (0.918 contre 0.888).
    """
    if not scores:
        return False
    return max(scores) >= seuil


def _demo() -> None:
    """Vérifie le modèle : dimensions, classement sémantique, multilingue.

    Ne teste volontairement pas `resultats_pertinents()`. Ces trois passages sont
    des phrases isolées, alors que le corpus contient des abstracts complets qui
    scorent structurellement plus haut : ici le bon passage sort à ~0.88, contre
    ~0.94 en conditions réelles. L'échelle n'est pas la même, et c'est en
    calibrant le seuil sur ce décor qu'on avait cassé la détection.

    La calibration se teste sur les vraies mesures : tests/test_pertinence.py.
    """
    passages = [
        "DNA alkylation lesion repair: outcomes and implications in cancer chemotherapy.",
        "Poxvirus Recombination. Genetic recombination modifies poxvirus genomes.",
        "The molecular biology of meiosis in plants.",
    ]
    vecs_docs = encoder(passages)
    assert len(vecs_docs[0]) == DIMENSIONS, \
        f"dimension attendue {DIMENSIONS}, obtenue {len(vecs_docs[0])}"

    def scores_pour(question: str) -> list[float]:
        q = encoder_question(question)
        return [sum(x * y for x, y in zip(q, d)) for d in vecs_docs]

    fr = scores_pour("reparation de l ADN apres dommage par alkylation")
    en = scores_pour("DNA repair after alkylation damage")
    hs = scores_pour("pizza recipe with pineapple")

    # Le bon passage doit arriver premier dans les deux langues.
    assert fr.index(max(fr)) == 0, f"classement FR incorrect : {fr}"
    assert en.index(max(en)) == 0, f"classement EN incorrect : {en}"
    # Le français ne doit plus être traité comme du bruit.
    assert max(fr) > 0.80, f"français trop faible : {max(fr):.3f}"

    # Le hors-sujet doit rester nettement en dessous, même sur ce petit décor.
    assert max(hs) < max(fr) - 0.05, \
        f"hors-sujet trop proche du pertinent : {max(hs):.3f} vs {max(fr):.3f}"

    print(f"OK — {DIMENSIONS} dimensions, multilingue")
    print(f"  FR pertinent : {max(fr):.3f}")
    print(f"  EN pertinent : {max(en):.3f}")
    print(f"  hors-sujet   : {max(hs):.3f}")
    print(f"\n  (seuil de pertinence = {SEUIL_PERTINENCE}, calibré sur le corpus réel —")
    print("   ces trois passages isolés scorent plus bas, cf. docstring)")


if __name__ == "__main__":
    _demo()
