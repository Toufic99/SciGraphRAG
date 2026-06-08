"""Reactome BioPAX extraction (validated for large Homo_sapiens.owl).

Goal:
- Keep about N human pathways (default 20)
- Extract Pathway and Protein nodes
- Extract Protein -[:PARTICIPATES_IN]-> Pathway relations
- Export JSON files:
  - reactome_nodes.json
  - reactome_edges.json

Usage:
    python src/ingest/fetch_reactome.py --input data/raw/reactome_human --out data/processed --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

BP_NS = "http://www.biopax.org/release/biopax-level3.owl#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

RDF_ID = "{" + RDF_NS + "}ID"
RDF_RESOURCE = "{" + RDF_NS + "}resource"

BP_TAG = "{" + BP_NS + "}"


def _local_resource(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("#"):
        return value[1:]
    return value


def _first_text(elem: ET.Element, child_name: str) -> str | None:
    for child in elem.findall(BP_TAG + child_name):
        if child.text and child.text.strip():
            return child.text.strip()
    return None


def _find_uniprot_from_text(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"\b([A-NR-Z][0-9][A-Z0-9]{3}[0-9])\b", text)
    return m.group(1) if m else None


def _iter_owl_files(input_dir: str) -> list[Path]:
    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    files = sorted([p for p in base.iterdir() if p.suffix.lower() in {".owl", ".rdf", ".xml"}])
    if not files:
        raise FileNotFoundError(f"No OWL/RDF/XML files found in: {input_dir}")
    return files


def _parse_biopax(path: Path):
    xref_map: dict[str, dict] = {}
    protein_ref_map: dict[str, dict] = {}
    protein_map: dict[str, dict] = {}
    reaction_map: dict[str, set[str]] = {}
    step_map: dict[str, set[str]] = {}
    pathway_map: dict[str, dict] = {}

    tree = ET.parse(str(path))
    root = tree.getroot()

    for elem in root.iter():
        tag = elem.tag

        if tag == BP_TAG + "UnificationXref":
            xid = elem.attrib.get(RDF_ID)
            if xid:
                db = _first_text(elem, "db")
                dbid = _first_text(elem, "id")
                xref_map[xid] = {"db": db, "id": dbid}

        elif tag == BP_TAG + "ProteinReference":
            pid = elem.attrib.get(RDF_ID)
            if pid:
                xrefs = []
                for child in elem.findall(BP_TAG + "xref"):
                    ref = _local_resource(child.attrib.get(RDF_RESOURCE))
                    if ref:
                        xrefs.append(ref)
                names = []
                for child in elem.findall(BP_TAG + "name"):
                    if child.text and child.text.strip():
                        names.append(child.text.strip())
                protein_ref_map[pid] = {"xrefs": xrefs, "names": names}

        elif tag == BP_TAG + "Protein":
            pid = elem.attrib.get(RDF_ID)
            if pid:
                display = _first_text(elem, "displayName")
                entity_ref_elem = elem.find(BP_TAG + "entityReference")
                entity_ref = _local_resource(entity_ref_elem.attrib.get(RDF_RESOURCE)) if entity_ref_elem is not None else None
                names = []
                for child in elem.findall(BP_TAG + "name"):
                    if child.text and child.text.strip():
                        names.append(child.text.strip())
                protein_map[pid] = {
                    "display": display,
                    "entity_ref": entity_ref,
                    "names": names,
                }

        elif tag == BP_TAG + "BiochemicalReaction":
            rid = elem.attrib.get(RDF_ID)
            if rid:
                proteins = set()
                for rel in ("left", "right"):
                    for child in elem.findall(BP_TAG + rel):
                        ref = _local_resource(child.attrib.get(RDF_RESOURCE))
                        if ref and ref.startswith("Protein"):
                            proteins.add(ref)
                reaction_map[rid] = proteins

        elif tag == BP_TAG + "PathwayStep":
            sid = elem.attrib.get(RDF_ID)
            if sid:
                processes = set()
                for child in elem.findall(BP_TAG + "stepProcess"):
                    ref = _local_resource(child.attrib.get(RDF_RESOURCE))
                    if ref:
                        processes.add(ref)
                step_map[sid] = processes

        elif tag == BP_TAG + "Pathway":
            pid = elem.attrib.get(RDF_ID)
            if pid:
                name = _first_text(elem, "displayName") or pid

                pathway_steps = []
                for child in elem.findall(BP_TAG + "pathwayOrder"):
                    ref = _local_resource(child.attrib.get(RDF_RESOURCE))
                    if ref:
                        pathway_steps.append(ref)

                components = []
                for child in elem.findall(BP_TAG + "pathwayComponent"):
                    ref = _local_resource(child.attrib.get(RDF_RESOURCE))
                    if ref:
                        components.append(ref)

                xrefs = []
                for child in elem.findall(BP_TAG + "xref"):
                    ref = _local_resource(child.attrib.get(RDF_RESOURCE))
                    if ref:
                        xrefs.append(ref)

                pathway_map[pid] = {
                    "name": name,
                    "steps": pathway_steps,
                    "components": components,
                    "xrefs": xrefs,
                }

    return xref_map, protein_ref_map, protein_map, reaction_map, step_map, pathway_map


def _pathway_stable_id(pathway_local_id: str, pdata: dict, xref_map: dict[str, dict]) -> str:
    for xid in pdata.get("xrefs", []):
        x = xref_map.get(xid)
        if not x:
            continue
        db = (x.get("db") or "").lower()
        dbid = x.get("id")
        if db == "reactome" and dbid:
            return dbid
    return pathway_local_id


def _protein_uniprot(prot_local_id: str, pdata: dict, protein_ref_map: dict[str, dict], xref_map: dict[str, dict]) -> tuple[str, str]:
    name = pdata.get("display") or (pdata.get("names") or [prot_local_id])[0]
    entity_ref = pdata.get("entity_ref")
    if entity_ref and entity_ref in protein_ref_map:
        ref_data = protein_ref_map[entity_ref]
        for xid in ref_data.get("xrefs", []):
            x = xref_map.get(xid)
            if not x:
                continue
            db = (x.get("db") or "").lower()
            dbid = x.get("id")
            if db == "uniprot" and dbid:
                return dbid, name
        for n in ref_data.get("names", []):
            uni = _find_uniprot_from_text(n)
            if uni:
                return uni, name

    for n in pdata.get("names", []):
        uni = _find_uniprot_from_text(n)
        if uni:
            return uni, name

    uni = _find_uniprot_from_text(name)
    if uni:
        return uni, name

    return prot_local_id, name


def extract_reactome(input_dir: str, out_dir: str, limit: int = 20) -> tuple[int, int, int]:
    files = _iter_owl_files(input_dir)

    all_xref: dict[str, dict] = {}
    all_pref: dict[str, dict] = {}
    all_prot: dict[str, dict] = {}
    all_rxn: dict[str, set[str]] = {}
    all_step: dict[str, set[str]] = {}
    all_pathway: dict[str, dict] = {}

    for file_path in files:
        print(f"Parsing {file_path}")
        xref_map, protein_ref_map, protein_map, reaction_map, step_map, pathway_map = _parse_biopax(file_path)
        all_xref.update(xref_map)
        all_pref.update(protein_ref_map)
        all_prot.update(protein_map)
        all_rxn.update(reaction_map)
        all_step.update(step_map)
        all_pathway.update(pathway_map)

    selected_pathway_keys = list(all_pathway.keys())[:limit]

    pathways = []
    for pkey in selected_pathway_keys:
        pdata = all_pathway[pkey]
        pathways.append(
            {
                "type": "Pathway",
                "id": _pathway_stable_id(pkey, pdata, all_xref),
                "name": pdata["name"],
                "source": "Reactome",
            }
        )

    pkey_to_public_id = {
        pkey: _pathway_stable_id(pkey, all_pathway[pkey], all_xref)
        for pkey in selected_pathway_keys
    }

    protein_nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()

    def collect_reactions_for_pathway(pathway_key: str, visited: set[str] | None = None) -> set[str]:
        visited = visited or set()
        if pathway_key in visited:
            return set()
        visited.add(pathway_key)

        pdata_local = all_pathway.get(pathway_key, {})
        found = set()

        for sid in pdata_local.get("steps", []):
            for proc in all_step.get(sid, set()):
                if proc in all_rxn:
                    found.add(proc)

        for comp in pdata_local.get("components", []):
            if comp in all_rxn:
                found.add(comp)
            if comp in all_pathway:
                found |= collect_reactions_for_pathway(comp, visited)

        return found

    for pkey in selected_pathway_keys:
        pathway_id = pkey_to_public_id[pkey]
        reaction_ids = collect_reactions_for_pathway(pkey)

        for rid in reaction_ids:
            for prot_local in all_rxn.get(rid, set()):
                if prot_local not in all_prot:
                    continue
                uni, pname = _protein_uniprot(prot_local, all_prot[prot_local], all_pref, all_xref)
                protein_nodes[uni] = {"type": "Protein", "uniprot": uni, "name": pname}
                edges.add((uni, "PARTICIPATES_IN", pathway_id))

    nodes = pathways + list(protein_nodes.values())
    edge_list = [
        {"source": s, "relation": r, "target": t}
        for s, r, t in sorted(edges)
    ]

    os.makedirs(out_dir, exist_ok=True)
    nodes_out = os.path.join(out_dir, "reactome_nodes.json")
    edges_out = os.path.join(out_dir, "reactome_edges.json")

    with open(nodes_out, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
    with open(edges_out, "w", encoding="utf-8") as f:
        json.dump(edge_list, f, ensure_ascii=False, indent=2)

    print(f"Pathways extracted: {len(pathways)}")
    print(f"Proteins extracted: {len(protein_nodes)}")
    print(f"Relationships extracted: {len(edge_list)}")
    print(f"Wrote {len(nodes)} reactome nodes to {nodes_out}")
    print(f"Wrote {len(edge_list)} PARTICIPATES_IN edges to {edges_out}")

    return len(pathways), len(protein_nodes), len(edge_list)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to Reactome BioPAX directory")
    parser.add_argument("--out", required=True, help="Output directory for processed JSON")
    parser.add_argument("--limit", type=int, default=20, help="Max pathways to keep")
    args = parser.parse_args()
    extract_reactome(args.input, args.out, args.limit)


if __name__ == "__main__":
    main()
