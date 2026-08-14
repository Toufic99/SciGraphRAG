# Project Summary

SciGraphRAG répond à un besoin simple mais central en bioinformatique: relier des connaissances biomédicales hétérogènes dans un graphe exploitable et interprétable. Les ontologies, les bases de voies biologiques (pathways) et les annotations de protéines sont souvent stockées dans des formats différents et difficiles à interroger de manière unifiée. Le projet montre comment convertir ces sources publiques en un graphe `Neo4j` cohérent, puis comment s'en servir pour répondre à des questions en langage naturel de façon traçable.

Les données proviennent de trois sources. Gene Ontology fournit les processus biologiques et leurs relations hiérarchiques `IS_A` et `PART_OF`. Reactome apporte les voies biologiques et les protéines impliquées, reliées par `PARTICIPATES_IN`. PubMed ajoute une couche textuelle: des abstracts rattachés aux concepts par la relation `MENTIONS`, qui rend possible la recherche sémantique. L'ensemble forme un graphe de 1 197 nœuds et 1 751 relations, avec 94 `BiologicalProcess`, 20 `Pathway`, 249 `Protein` et 834 `Publication`.

Les termes GO dépréciés sont exclus à l'extraction. Ils représentaient 43 % des concepts initialement importés, sans contribuer à la hiérarchie: aucun d'eux ne portait de relation `IS_A` ou `PART_OF`, et la littérature ne référence pas leurs libellés. Ce filtrage illustre une exigence propre au travail sur ontologies: une source publique curatée n'est pas pour autant directement exploitable.

## Versions des données (reproductibilité)

- `go.owl` (Gene Ontology) — fichier local `data/raw/go.owl`, last modified: 2026-06-07T17:27:42
- `Homo_sapiens.owl` (Reactome) — fichier local `data/raw/reactome_human/Homo_sapiens.owl`, last modified: 2026-03-25T03:45:10
- PubMed — API NCBI E-utilities, import des 114 concepts du graphe × 10 abstracts (étiquette NCBI respectée)

Le pipeline est volontairement lisible : parsing `OWL`/BioPAX, extraction des relations utiles via `SPARQL`, import dans `Neo4j`, puis requêtes `Cypher` et visualisation de sous-graphes. Une démonstration est fournie sous forme de notebook avec captures d'écran générées automatiquement, ce qui rend le projet facile à présenter dans un cadre académique.

## De l'exploration au questionnement

La seconde partie du projet transforme ce graphe en moteur de questions-réponses. Les abstracts sont encodés localement (`intfloat/multilingual-e5-large`, 1024 dimensions) et stockés directement sur les nœuds `:Publication`, via l'index vectoriel natif de `Neo4j` — sans base vectorielle séparée. Une question déclenche alors trois étapes : recherche vectorielle, remontée aux concepts mentionnés, puis exploration de leur voisinage ontologique.

C'est cette troisième étape qui distingue l'approche d'un `RAG` classique. Sur la question *DNA repair after alkylation damage*, le système restitue la chaîne `DNA alkylation repair --IS_A--> DNA repair`, qui ne figure dans aucun abstract : elle provient de la structure curatée de Gene Ontology. La réponse devient vérifiable, puisque l'utilisateur peut contrôler l'origine de chaque affirmation — un `PMID` pour un fait de littérature, une relation nommée pour un fait structurel.

Le système signale également les questions que le corpus ne couvre pas, au lieu de présenter le bruit le mieux classé comme une réponse. Ce seuil de non-couverture a été calibré sur des mesures réelles et non sur un jeu d'essai réduit, une distinction qui s'est avérée décisive : le premier critère retenu, fondé sur l'écart entre le meilleur score et la moyenne, était valide sur trois passages isolés mais inopérant sur le corpus complet.

Les résultats obtenus montrent qu'un graphe de connaissances léger mais bien structuré suffit déjà à produire des explorations explicables et des réponses sourcées. Le projet démontre des compétences directement pertinentes pour une thèse INRAE : intégration de données biomédicales, modélisation de graphe, `SPARQL`, `Neo4j`/`Cypher`, recherche vectorielle et `GraphRAG`, validation de pipelines et communication scientifique par la visualisation.
