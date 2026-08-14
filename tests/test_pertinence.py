"""Le détecteur de pertinence doit trancher sur le vrai corpus, pas sur une maquette.

Ces fixtures ne sont pas inventées : ce sont les scores réellement renvoyés par
l'index vectoriel des 834 publications (top-5 par question, modèle
multilingual-e5-large). C'est le point central de ce fichier.

Elles ont été remesurées après l'élargissement du corpus (428 → 834 publications) :
les deux populations ont glissé de ~0,002 vers le haut, mais la séparation a tenu
(0,9209 contre 0,8903, marge 0,0306) et le seuil de 0,90 reste valide.

La version précédente de `resultats_pertinents()` avait été calibrée dans un
`_demo()` sur trois passages choisis à la main et volontairement très éloignés
les uns des autres. Dans ce décor, le meilleur résultat se détachait de ~0,05 de
la moyenne, et l'écart semblait être un bon signal. Sur le vrai corpus, l'index
renvoie les cinq voisins les plus proches — qui se ressemblent tous entre eux par
construction. L'écart s'écrase alors autour de 0,005, que la question soit
pertinente ou absurde, et ne sépare plus rien.

D'où la règle : toute fixture de ce fichier doit venir d'une mesure sur le corpus.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from kg.embeddings import resultats_pertinents

# Scores mesurés sur le corpus (top-5). Questions dont la réponse s'y trouve.
# Les deux dernières portent sur des concepts arrivés avec l'élargissement à
# 184 concepts : la calibration ne doit pas tenir qu'aux questions d'origine.
DANS_LE_CORPUS = [
    ([0.9448, 0.9407, 0.9345, 0.9338, 0.9334], "DNA repair after alkylation damage"),
    ([0.9548, 0.9482, 0.9480, 0.9461, 0.9421], "apoptosis regulation"),
    ([0.9395, 0.9381, 0.9379, 0.9345, 0.9312], "base excision repair"),
    ([0.9218, 0.9209, 0.9205, 0.9187, 0.9181], "reparation de l ADN"),
    ([0.9239, 0.9235, 0.9208, 0.9200, 0.9196], "processus apoptotique"),
    ([0.9338, 0.9313, 0.9246, 0.9191, 0.9165], "cell cycle checkpoint"),
    ([0.9209, 0.9195, 0.9189, 0.9185, 0.9182], "signalisation cellulaire et proteines"),
    ([0.9498, 0.9486, 0.9341, 0.9335, 0.9324], "mitochondrial membrane permeabilization"),
    ([0.9455, 0.9346, 0.9336, 0.9322, 0.9285], "transcription factor binding"),
    ([0.9255, 0.9231, 0.9225, 0.9213, 0.9208], "oxidative stress response"),
    ([0.9369, 0.9342, 0.9333, 0.9295, 0.9294], "regulation of cellular response to stress"),
    ([0.9491, 0.9446, 0.9439, 0.9424, 0.9420], "interstrand cross-link repair"),
]

# Mêmes conditions, questions sans aucun rapport avec le corpus biomédical.
# « comment reparer une voiture » est le cas le plus serré (0,8903) : en français,
# « réparer » partage sa sémantique avec les nombreux concepts de *DNA repair*
# du corpus. C'est la question à surveiller si le seuil doit un jour bouger.
HORS_CORPUS = [
    ([0.8882, 0.8869, 0.8854, 0.8836, 0.8835], "recette de pizza a l ananas"),
    ([0.8678, 0.8644, 0.8629, 0.8628, 0.8622], "quel est le prix du bitcoin"),
    ([0.8903, 0.8878, 0.8850, 0.8840, 0.8839], "comment reparer une voiture"),
    ([0.8678, 0.8670, 0.8643, 0.8642, 0.8635], "meilleur hotel a Paris"),
    ([0.8768, 0.8764, 0.8762, 0.8761, 0.8743], "resultats du championnat de football"),
    ([0.8798, 0.8780, 0.8771, 0.8749, 0.8747], "comment tricoter une echarpe"),
    ([0.8805, 0.8798, 0.8787, 0.8773, 0.8769], "horaires des trains pour Lyon"),
    ([0.8767, 0.8766, 0.8728, 0.8723, 0.8721], "comment investir en bourse"),
]


@pytest.mark.parametrize("scores,question", DANS_LE_CORPUS, ids=[q for _, q in DANS_LE_CORPUS])
def test_question_couverte_est_acceptee(scores, question):
    """Une question dont le corpus contient la réponse ne doit pas être rejetée.

    C'est le cas que l'ancienne implémentation ratait : la démo affichait
    « le corpus ne couvre probablement pas cette question » sur sa propre
    question vedette, tout en remontant cinq publications pertinentes.
    """
    assert resultats_pertinents(scores), (
        f"question pertinente rejetée : {question!r} (meilleur score {max(scores):.4f})"
    )


@pytest.mark.parametrize("scores,question", HORS_CORPUS, ids=[q for _, q in HORS_CORPUS])
def test_question_hors_sujet_est_rejetee(scores, question):
    """Une question sans rapport doit être signalée, pas habillée en réponse."""
    assert not resultats_pertinents(scores), (
        f"question hors-sujet acceptée : {question!r} (meilleur score {max(scores):.4f})"
    )


def test_la_separation_reste_franche():
    """Garde-fou de calibration : les deux populations ne doivent pas se toucher.

    Si un réimport élargit le corpus ou si le modèle d'embedding change, ce test
    casse avant les autres et signale qu'il faut recalibrer sur de nouvelles
    mesures — au lieu de laisser le seuil dériver en silence.
    """
    pire_pertinente = min(max(s) for s, _ in DANS_LE_CORPUS)
    meilleure_hors_sujet = max(max(s) for s, _ in HORS_CORPUS)
    assert pire_pertinente > meilleure_hors_sujet, (
        f"les populations se chevauchent : pertinente {pire_pertinente:.4f} "
        f"<= hors-sujet {meilleure_hors_sujet:.4f}"
    )


def test_liste_vide_est_rejetee():
    """Aucun résultat n'est pas une réponse."""
    assert not resultats_pertinents([])
