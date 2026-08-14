"""Récupération d'abstracts PubMed pour enrichir le graphe d'une couche textuelle.

Cette couche est la brique manquante du pipeline GraphRAG annoncé dans le README :
elle relie chaque concept du graphe (BiologicalProcess, Pathway) aux publications
qui en parlent, afin de permettre un retrieval hybride sous-graphe + texte.

API utilisée : NCBI E-utilities (publique, sans clé).
Étiquette NCBI respectée : identification via `tool` et `email`, 3 requêtes/s maximum.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "SciGraphRAG"
EMAIL = "toufic.bathich123@gmail.com"

# NCBI tolère 3 req/s sans clé API. On reste volontairement en dessous.
PAUSE = 0.4
TIMEOUT = 25


@dataclass
class Publication:
    """Un abstract PubMed rattaché à un concept du graphe."""

    pmid: str
    titre: str
    abstract: str
    annee: int | None
    journal: str | None
    concept: str          # label du nœud GO/Reactome à l'origine de la requête

    @property
    def texte(self) -> str:
        """Texte complet utilisé pour l'embedding."""
        return f"{self.titre}\n\n{self.abstract}".strip()


def _get(endpoint: str, params: dict) -> requests.Response | None:
    params = {**params, "tool": TOOL, "email": EMAIL}
    try:
        r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=TIMEOUT)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def rechercher_pmids(terme: str, limite: int = 20) -> list[str]:
    """Retourne les PMID les plus pertinents pour un terme (esearch)."""
    time.sleep(PAUSE)
    r = _get("esearch.fcgi", {
        "db": "pubmed",
        "term": terme,
        "retmax": limite,
        "retmode": "json",
        "sort": "relevance",
    })
    if r is None:
        return []
    try:
        return r.json()["esearchresult"].get("idlist", [])
    except (ValueError, KeyError):
        return []


def _texte(noeud: ET.Element | None) -> str:
    """Concatène le texte d'un nœud XML, y compris ses enfants (abstracts structurés)."""
    if noeud is None:
        return ""
    return " ".join(noeud.itertext()).strip()


def charger_abstracts(pmids: list[str], concept: str) -> list[Publication]:
    """Télécharge les abstracts complets pour une liste de PMID (efetch)."""
    if not pmids:
        return []

    time.sleep(PAUSE)
    r = _get("efetch.fcgi", {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    })
    if r is None:
        return []

    try:
        racine = ET.fromstring(r.content)
    except ET.ParseError:
        return []

    publications: list[Publication] = []
    for art in racine.findall(".//PubmedArticle"):
        pmid = _texte(art.find(".//PMID"))
        titre = _texte(art.find(".//ArticleTitle"))
        # Un abstract peut être découpé en sections (Background, Methods...)
        morceaux = [_texte(a) for a in art.findall(".//Abstract/AbstractText")]
        abstract = " ".join(m for m in morceaux if m)

        if not pmid or not abstract:
            continue  # sans texte, la publication n'apporte rien au retrieval

        annee_txt = _texte(art.find(".//PubDate/Year"))
        publications.append(Publication(
            pmid=pmid,
            titre=titre,
            abstract=abstract,
            annee=int(annee_txt) if annee_txt.isdigit() else None,
            journal=_texte(art.find(".//Journal/Title")) or None,
            concept=concept,
        ))

    return publications


def collecter_pour_concept(concept: str, limite: int = 20) -> list[Publication]:
    """Chaîne complète pour un concept : recherche puis récupération des abstracts."""
    pmids = rechercher_pmids(concept, limite=limite)
    return charger_abstracts(pmids, concept=concept)


def _demo() -> None:
    """Vérification minimale : le module doit ramener des abstracts exploitables."""
    pubs = collecter_pour_concept("apoptotic process", limite=5)
    assert pubs, "aucune publication récupérée — API PubMed injoignable ?"
    for p in pubs:
        assert p.pmid.isdigit(), f"PMID invalide : {p.pmid!r}"
        assert len(p.abstract) > 50, f"abstract trop court pour {p.pmid}"
    print(f"OK — {len(pubs)} publications pour 'apoptotic process'")
    ex = pubs[0]
    print(f"  PMID {ex.pmid} ({ex.annee}) — {ex.journal}")
    print(f"  {ex.titre[:90]}")
    print(f"  {ex.abstract[:180]}...")


if __name__ == "__main__":
    _demo()
