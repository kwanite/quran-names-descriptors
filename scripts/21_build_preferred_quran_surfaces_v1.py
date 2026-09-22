#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

EXPECTED_IDENTITIES = 225
EXPECTED_OCCURRENCES = 5037
EXPECTED_SURFACES = 404

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def verse_sort_key(row):
    s, a = str(row["verse_key"]).split(":")
    return (int(s), int(a), int(row.get("start_offset") or 0), str(row["occurrence_id"]))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    repo = a.repo.resolve()

    corpus = repo / "runs/phase1_full_v3_2_1/semantic_exclusions_v2"
    out = repo / "runs/phase1_full_v3_2_1/finalization_v1/preferred_quran_surfaces.json"

    if out.exists() and not a.overwrite:
        raise SystemExit(f"Refusing to overwrite existing output: {out}")

    freq = load(corpus / "lexical_frequency.json")
    occ = load(corpus / "descriptor_occurrences_lexical.json")
    surf = load(corpus / "surface_to_lexeme_map_reviewed.json")

    identities = [x["lexical_identity_arabic"] for x in freq["lexical_identities"]]
    rows = occ["occurrences"]

    if len(identities) != EXPECTED_IDENTITIES:
        raise SystemExit(f"Expected {EXPECTED_IDENTITIES} identities, got {len(identities)}")
    if len(rows) != EXPECTED_OCCURRENCES:
        raise SystemExit(f"Expected {EXPECTED_OCCURRENCES} occurrences, got {len(rows)}")
    if int(surf.get("surface_count", -1)) != EXPECTED_SURFACES:
        raise SystemExit(f"Expected {EXPECTED_SURFACES} surfaces, got {surf.get('surface_count')}")

    by_identity = defaultdict(list)
    for r in rows:
        by_identity[r["lexical_identity_arabic"]].append(r)

    result = []
    for ident in identities:
        rws = sorted(by_identity[ident], key=verse_sort_key)
        if not rws:
            raise SystemExit(f"No occurrences for identity: {ident}")
        counts = Counter(r["surface_arabic"] for r in rws)
        earliest = {}
        for r in rws:
            earliest.setdefault(r["surface_arabic"], r)

        # Deterministic display rule:
        # 1. most frequent exact Quran surface;
        # 2. earliest Quran occurrence;
        # 3. Unicode codepoint order as a final deterministic tie-break.
        candidates = sorted(
            counts,
            key=lambda s: (
                -counts[s],
                verse_sort_key(earliest[s]),
                s,
            ),
        )
        preferred = candidates[0]
        first = earliest[preferred]

        result.append({
            "lexical_identity_arabic": ident,
            "preferred_quran_surface": preferred,
            "preferred_surface_numbered_occurrence_count": counts[preferred],
            "first_preferred_occurrence_id": first["occurrence_id"],
            "first_preferred_verse_key": first["verse_key"],
            "candidate_surfaces": [
                {
                    "surface_arabic": s,
                    "numbered_occurrence_count": counts[s],
                    "first_occurrence_id": earliest[s]["occurrence_id"],
                    "first_verse_key": earliest[s]["verse_key"],
                }
                for s in candidates
            ],
        })

    if len(result) != EXPECTED_IDENTITIES:
        raise SystemExit("Preferred-surface output count mismatch.")

    # Every selected display form must be an actually attested member surface.
    for x in result:
        members = {c["surface_arabic"] for c in x["candidate_surfaces"]}
        if x["preferred_quran_surface"] not in members:
            raise SystemExit(f"Unattested preferred surface: {x['lexical_identity_arabic']}")

    output = {
        "version": "preferred-quran-surfaces-v1",
        "source_semantic_version": "semantic-exclusions-v2",
        "selection_rule": [
            "Choose only from exact Quran-attested surfaces belonging to the final lexical identity.",
            "Prefer the surface with the highest retained numbered-verse occurrence count.",
            "Break frequency ties by earliest Quran occurrence, then Unicode codepoint order.",
            "Never synthesize or normalize a display surface that is unattested.",
        ],
        "identity_count": len(result),
        "records": result,
    }
    dump(out, output)
    print("PREFERRED QURAN SURFACES: PASS")
    print(f"Identities: {len(result)}")
    print(f"Output: {out}")

if __name__ == "__main__":
    main()
