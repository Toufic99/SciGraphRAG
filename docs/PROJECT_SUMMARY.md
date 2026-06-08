# Project Summary

SciGraphRAG répond à un besoin simple mais central en bioinformatique: relier des connaissances biomédicales hétérogènes dans un graphe exploitable et interprétable. Les ontologies, les bases de voies biologiques (pathways) et les annotations de protéines sont souvent stockées dans des formats différents et difficiles à interroger de manière unifiée. Le projet montre comment convertir ces sources publiques en un graphe `Neo4j` cohérent pour soutenir une exploration de type `GraphRAG`.

Les données proviennent de Gene Ontology et de Reactome. Gene Ontology fournit les processus biologiques et leurs relations hiérarchiques `IS_A` et `PART_OF`. Reactome apporte les voies biologiques (pathways) et les protéines impliquées, reliées par `PARTICIPATES_IN`. L’ensemble a été intégré dans un même graphe de 453 nœuds et 823 relations, avec 164 `BiologicalProcess`, 40 `Pathway` et 249 `Protein`.

## Versions des données (reproductibilité)

- `go.owl` (Gene Ontology) — fichier local `data/raw/go.owl`, last modified: 2026-06-07T17:27:42
- `Homo_sapiens.owl` (Reactome) — fichier local `data/raw/reactome_human/Homo_sapiens.owl`, last modified: 2026-03-25T03:45:10

Le pipeline est volontairement lisible : parsing `OWL`/BioPAX, extraction des relations utiles via `SPARQL`, import dans `Neo4j`, puis requêtes `Cypher` et visualisation de sous-graphes. La démonstration finale est fournie sous forme de notebook avec captures d’écran générées automatiquement, ce qui rend le projet facile à présenter dans un cadre académique.

Les résultats obtenus montrent qu’un graphe de connaissances léger mais bien structuré suffit déjà à produire des explorations explicables et des vues de synthèse. Le projet démontre des compétences directement pertinentes pour une thèse INRAE : intégration de données biomédicales, modélisation de graphe, `SPARQL`, `Neo4j`/`Cypher`, validation de pipelines et communication scientifique par la visualisation.