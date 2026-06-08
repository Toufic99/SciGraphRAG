# Architecture

```mermaid
flowchart TD
    GO[Gene Ontology (OWL/RDF)] --> RDF[rdflib]
    RDF --> SPARQL[SPARQL]
    SPARQL --> NEO4J[Neo4j]

    REACTOME[Reactome (BioPAX / OWL/RDF)] --> NEO4J

    NEO4J --> CYPHER[Cypher]
    CYPHER --> VIS[Visualisation]
```

## Lecture du schéma


- `Gene Ontology` est analysée comme ressource `OWL/RDF` avec `rdflib`.
- Les triplets utiles sont extraits par `SPARQL` avant import dans `Neo4j`.
- `Reactome` complète le graphe avec les voies biologiques (pathways) et les protéines.
- Les requêtes `Cypher` servent à extraire des sous-graphes explicables.
- Les sous-graphes sont ensuite visualisés dans le notebook de démonstration.

Ce schéma correspond au cœur du portfolio: un pipeline de connaissances publiques transformées en graphe exploitable pour la recherche et la démonstration scientifique.
