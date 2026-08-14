"""Retrieval hybride : similarité sémantique + traversée du graphe.

C'est la brique qui distingue ce pipeline d'un RAG classique. Un RAG ordinaire
renvoie des morceaux de texte isolés ; ici, on part des abstracts les plus proches
sémantiquement, on remonte aux concepts qu'ils mentionnent, puis on explore leur
voisinage dans l'ontologie. La réponse finale peut donc citer un chemin vérifiable
(« ce processus est un sous-type de celui-là ») et pas seulement un extrait.

Ordre de la recherche :
  1. Recherche vectorielle sur les :Publication
  2. Concepts mentionnés par ces publications
  3. Voisinage ontologique de ces concepts (IS_A, PART_OF, PARTICIPATES_IN)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg.embeddings import NOM_INDEX, encoder_question, resultats_pertinents

# --- Étape 1 : publications sémantiquement proches -------------------------

PUBLICATIONS_PROCHES = f"""
CALL db.index.vector.queryNodes('{NOM_INDEX}', $k, $vecteur)
YIELD node AS pub, score
RETURN pub.pmid AS pmid, pub.title AS titre, pub.abstract AS abstract,
       pub.year AS annee, pub.journal AS journal, score
ORDER BY score DESC
"""

# --- Étape 2 : concepts rattachés à ces publications -----------------------

CONCEPTS_DES_PUBLICATIONS = """
MATCH (pub:Publication)-[:MENTIONS]->(c)
WHERE pub.pmid IN $pmids
RETURN DISTINCT
       coalesce(c.label, c.name) AS nom,
       labels(c)[0] AS type,
       c.id AS id,
       count(DISTINCT pub) AS nb_publications
ORDER BY nb_publications DESC
"""

# --- Étape 3 : voisinage ontologique ---------------------------------------
# On garde la direction de la relation : elle porte le sens (A IS_A B ≠ B IS_A A).

VOISINAGE_GO = """
MATCH (c:BiologicalProcess) WHERE c.id IN $ids
OPTIONAL MATCH (c)-[r:IS_A|PART_OF]->(parent:BiologicalProcess)
OPTIONAL MATCH (enfant:BiologicalProcess)-[r2:IS_A|PART_OF]->(c)
RETURN c.label AS concept,
       collect(DISTINCT {relation: type(r),  cible: parent.label, sens: 'vers'})  AS parents,
       collect(DISTINCT {relation: type(r2), cible: enfant.label, sens: 'depuis'}) AS enfants
"""

VOISINAGE_PATHWAY = """
MATCH (p:Pathway) WHERE p.id IN $ids
OPTIONAL MATCH (prot:Protein)-[:PARTICIPATES_IN]->(p)
RETURN p.name AS pathway,
       collect(DISTINCT prot.name)[0..12] AS proteines,
       count(DISTINCT prot) AS nb_proteines
"""


@dataclass
class Publication:
    pmid: str
    titre: str
    abstract: str
    annee: int | None
    journal: str | None
    score: float


@dataclass
class Concept:
    nom: str
    type: str
    id: str
    nb_publications: int


@dataclass(frozen=True)
class Relation:
    """Un lien du graphe, avec le sens de lecture conservé.

    Le sens porte l'information : « ce concept relève de X » et « ce concept se
    décline en Y » répondent à deux questions différentes. Sérialiser en chaîne
    de caractères trop tôt la perdait, alors qu'un concept a typiquement 2 parents
    et 20 enfants — les mélanger noie la généralisation sous les spécialisations.
    """

    source: str
    type: str
    cible: str
    sens: str
    """`generalisation` (vers le parent), `specialisation` (vers l'enfant),
    ou `composition` (voie biologique et ses protéines)."""

    def __str__(self) -> str:
        return f"{self.source} --{self.type}--> {self.cible}"


@dataclass
class Contexte:
    """Contexte structuré transmis au LLM à l'étape suivante."""

    question: str
    publications: list[Publication] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    pertinent: bool = True
    """Faux quand les scores sont plats : le corpus ne couvre pas la question.

    Distinction importante — « aucun résultat » et « des résultats sans rapport »
    doivent être signalés différemment, sinon l'outil invente une réponse
    à partir du bruit le mieux classé.
    """

    def concepts_du_graphe_seul(self) -> set[str]:
        """Concepts apparus par la traversée, absents des publications retrouvées.

        C'est la mesure de ce qu'un RAG ordinaire ne peut pas produire : ces
        concepts ne figurent dans aucun abstract remonté par la recherche
        vectorielle. Sur « réparation de l'ADN », ils représentent 25 des 30
        concepts affichés.
        """
        depuis_publications = {c.nom for c in self.concepts}
        dans_chemins: set[str] = set()
        for r in self.relations:
            # En composition, la source est un résumé de protéines, pas un concept.
            if r.sens == "composition":
                dans_chemins.add(r.cible)
            else:
                dans_chemins.update((r.source, r.cible))
        return dans_chemins - depuis_publications

    def en_texte(self, extrait: int = 700) -> str:
        """Sérialise le contexte pour un prompt LLM, structure d'abord."""
        blocs = []

        if not self.pertinent:
            blocs.append(
                "AVERTISSEMENT : les scores de similarité sont plats. Le corpus "
                "ne semble pas couvrir cette question. Les éléments ci-dessous "
                "sont les plus proches trouvés, mais ils peuvent être hors sujet."
            )

        if self.concepts:
            lignes = [f"- {c.nom} ({c.type}, cité par {c.nb_publications} publication(s))"
                      for c in self.concepts]
            blocs.append("CONCEPTS DU GRAPHE\n" + "\n".join(lignes))

        if self.relations:
            blocs.append("RELATIONS ONTOLOGIQUES\n" + "\n".join(f"- {r}" for r in self.relations))

        if self.publications:
            lignes = []
            for p in self.publications:
                lignes.append(
                    f"[PMID {p.pmid}] ({p.annee}, {p.journal or 'journal inconnu'}) "
                    f"— pertinence {p.score:.3f}\n"
                    f"  {p.titre}\n  {p.abstract[:extrait]}"
                )
            blocs.append("PUBLICATIONS\n" + "\n\n".join(lignes))

        return "\n\n".join(blocs)


def recuperer_contexte(client, question: str, k: int = 5) -> Contexte:
    """Assemble le contexte hybride pour une question en langage naturel."""
    ctx = Contexte(question=question)

    vecteur = encoder_question(question)
    lignes = client.run_query(PUBLICATIONS_PROCHES, {"k": k, "vecteur": vecteur})
    ctx.publications = [
        Publication(r["pmid"], r["titre"], r["abstract"] or "",
                    r["annee"], r["journal"], r["score"])
        for r in lignes
    ]
    if not ctx.publications:
        ctx.pertinent = False
        return ctx

    ctx.pertinent = resultats_pertinents([p.score for p in ctx.publications])

    pmids = [p.pmid for p in ctx.publications]
    ctx.concepts = [
        Concept(r["nom"], r["type"], r["id"], r["nb_publications"])
        for r in client.run_query(CONCEPTS_DES_PUBLICATIONS, {"pmids": pmids})
    ]

    ids_go = [c.id for c in ctx.concepts if c.type == "BiologicalProcess"]
    ids_pw = [c.id for c in ctx.concepts if c.type == "Pathway"]

    if ids_go:
        for r in client.run_query(VOISINAGE_GO, {"ids": ids_go}):
            for lien in r["parents"]:
                if lien.get("cible"):
                    ctx.relations.append(Relation(
                        r["concept"], lien["relation"], lien["cible"], "generalisation"))
            for lien in r["enfants"]:
                if lien.get("cible"):
                    ctx.relations.append(Relation(
                        lien["cible"], lien["relation"], r["concept"], "specialisation"))

    if ids_pw:
        for r in client.run_query(VOISINAGE_PATHWAY, {"ids": ids_pw}):
            if r["nb_proteines"]:
                prots = ", ".join(p for p in r["proteines"] if p)
                ctx.relations.append(Relation(
                    f"{r['nb_proteines']} protéine(s) : {prots}",
                    "PARTICIPATES_IN", r["pathway"], "composition"))

    # Deux publications peuvent mentionner le même concept : on dédoublonne
    # en conservant l'ordre d'apparition.
    ctx.relations = list(dict.fromkeys(ctx.relations))
    return ctx


def _demo() -> None:
    """Vérifie que le contexte hybride contient bien les trois niveaux."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from dotenv import load_dotenv
    from kg.neo4j_client import Neo4jClient

    load_dotenv()
    client = Neo4jClient()
    client.connect()

    ctx = recuperer_contexte(client, "DNA repair after alkylation damage", k=5)
    assert ctx.publications, "aucune publication récupérée"
    assert ctx.concepts, "aucun concept rattaché — la relation MENTIONS manque ?"

    print(f"OK — question : {ctx.question}")
    print(f"  {len(ctx.publications)} publications "
          f"(meilleur score {ctx.publications[0].score:.3f})")
    print(f"  {len(ctx.concepts)} concepts")
    print(f"  {len(ctx.relations)} relations ontologiques")
    if ctx.relations:
        print("\n  Exemples de chemins explicables :")
        for r in ctx.relations[:5]:
            print(f"    {r}")
    client.close()


if __name__ == "__main__":
    _demo()
