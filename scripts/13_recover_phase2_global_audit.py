#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def collect_output_text(obj: Any) -> list[str]:
    pieces = []

    def walk(x: Any):
        if isinstance(x, dict):
            if x.get("type") == "output_text" and isinstance(x.get("text"), str):
                pieces.append(x["text"])
            for value in x.values():
                walk(value)
        elif isinstance(x, list):
            for value in x:
                walk(value)

    walk(obj)
    return pieces


def collect_refusals(obj: Any) -> list[str]:
    refusals = []

    def walk(x: Any):
        if isinstance(x, dict):
            if x.get("type") == "refusal":
                value = x.get("refusal") or x.get("text")
                if isinstance(value, str):
                    refusals.append(value)
            for value in x.values():
                walk(value)
        elif isinstance(x, list):
            for value in x:
                walk(value)

    walk(obj)
    return refusals


def validate_corrections(
    current_map: dict[str, str],
    corrections: Any,
) -> list[dict[str, Any]]:
    findings = []

    if not isinstance(corrections, list):
        return [{"code": "CORRECTIONS_NOT_LIST"}]

    seen = set()

    for i, row in enumerate(corrections):
        if not isinstance(row, dict):
            findings.append({
                "code": "CORRECTION_NOT_OBJECT",
                "index": i,
            })
            continue

        surface = row.get("surface_arabic")
        old = row.get("from_identity")
        new = row.get("to_identity")

        if surface not in current_map:
            findings.append({
                "code": "UNKNOWN_SURFACE",
                "index": i,
                "surface_arabic": surface,
            })
            continue

        if surface in seen:
            findings.append({
                "code": "DUPLICATE_CORRECTION_SURFACE",
                "surface_arabic": surface,
            })
        seen.add(surface)

        if old != current_map[surface]:
            findings.append({
                "code": "FROM_IDENTITY_MISMATCH",
                "surface_arabic": surface,
                "expected": current_map[surface],
                "actual": old,
            })

        if not isinstance(new, str) or not new.strip():
            findings.append({
                "code": "INVALID_TO_IDENTITY",
                "surface_arabic": surface,
                "value": new,
            })
        elif new != new.strip():
            findings.append({
                "code": "TO_IDENTITY_OUTER_WHITESPACE",
                "surface_arabic": surface,
                "value": new,
            })
        elif new == old:
            findings.append({
                "code": "NO_OP_CORRECTION",
                "surface_arabic": surface,
            })

    return findings


def build_groups(mappings: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: OrderedDict[str, list[str]] = OrderedDict()
    for row in mappings:
        groups.setdefault(row["lexical_identity_arabic"], [])
        groups[row["lexical_identity_arabic"]].append(row["surface_arabic"])
    return [
        {
            "lexical_identity_arabic": identity,
            "member_surfaces": members,
        }
        for identity, members in groups.items()
    ]


def assert_core_invariants(mapping_by_surface: dict[str, str]) -> None:
    for surface in ("اللَّهُ", "اللَّهَ", "اللَّهِ", "لِلَّهِ", "آللَّهُ"):
        if surface in mapping_by_surface and mapping_by_surface[surface] != "اللَّه":
            raise RuntimeError(
                f"Allah invariant failed: {surface} -> "
                f"{mapping_by_surface[surface]!r}"
            )

    if (
        "قَدِيرٌ" in mapping_by_surface
        and "قَادِرٍ" in mapping_by_surface
        and mapping_by_surface["قَدِيرٌ"] == mapping_by_surface["قَادِرٍ"]
    ):
        raise RuntimeError(
            "Derivational invariant failed: قَدِيرٌ and قَادِرٍ merged."
        )

    if (
        "رَبِّ الْعَالَمِينَ" in mapping_by_surface
        and mapping_by_surface["رَبِّ الْعَالَمِينَ"] == "رَبّ"
    ):
        raise RuntimeError(
            "Multiword invariant failed: رَبِّ الْعَالَمِينَ -> رَبّ."
        )

    for surface in ("رَبُّكَ", "رَبَّكَ", "رَبِّكَ", "رَبِّي", "رَبَّنَا"):
        if surface in mapping_by_surface and mapping_by_surface[surface] != "رَبّ":
            raise RuntimeError(
                f"Rabb invariant failed: {surface} -> "
                f"{mapping_by_surface[surface]!r}"
            )


def finalize(
    run_dir: Path,
    out_dir: Path,
    corrections: list[dict[str, Any]],
    usage: Any,
) -> None:
    mapping_dir = run_dir / "phase2_surface_mapping_sol_v2"
    clean_prep = run_dir / "phase2_preparation_clean_v1"

    map_path = mapping_dir / "surface_to_lexeme_map.json"
    clean_input_path = (
        clean_prep / "phase2_normalization_v1" / "model_input.json"
    )
    occurrence_path = clean_prep / "phase1_occurrence_ledger.json"

    mapping_doc = read_json(map_path)
    mappings = mapping_doc["mappings"]
    clean_input = read_json(clean_input_path)
    candidates = clean_input["candidates"]

    clean_surfaces = [x["surface_arabic"] for x in candidates]
    mapped_surfaces = [x["surface_arabic"] for x in mappings]

    if mapped_surfaces != clean_surfaces:
        raise RuntimeError(
            "Saved Phase-2 mapping no longer exactly matches clean input."
        )

    current_map = {
        row["surface_arabic"]: row["lexical_identity_arabic"]
        for row in mappings
    }

    findings = validate_corrections(current_map, corrections)
    if findings:
        write_json(out_dir / "recovery_validation_findings.json", findings)
        raise RuntimeError(
            "Recovered corrections failed deterministic validation. "
            "See recovery_validation_findings.json."
        )

    reviewed_map = copy.deepcopy(current_map)
    for row in corrections:
        reviewed_map[row["surface_arabic"]] = row["to_identity"]

    assert_core_invariants(reviewed_map)

    reviewed_mappings = [
        {
            "surface_arabic": surface,
            "lexical_identity_arabic": reviewed_map[surface],
        }
        for surface in clean_surfaces
    ]
    reviewed_groups = build_groups(reviewed_mappings)

    occurrence_doc = read_json(occurrence_path)
    occurrences = occurrence_doc["occurrences"]
    if len(occurrences) != 5117:
        raise RuntimeError(
            f"Expected 5117 clean occurrences, found {len(occurrences)}."
        )

    enriched = []
    lexical_occurrence_counts = Counter()
    lexical_surface_sets = defaultdict(set)

    for occurrence in occurrences:
        surface = occurrence["surface_arabic"]
        identity = reviewed_map[surface]
        row = copy.deepcopy(occurrence)
        row["lexical_identity_arabic"] = identity
        enriched.append(row)
        lexical_occurrence_counts[identity] += 1
        lexical_surface_sets[identity].add(surface)

    lexical_frequency = []
    for group in reviewed_groups:
        identity = group["lexical_identity_arabic"]
        lexical_frequency.append({
            "lexical_identity_arabic": identity,
            "occurrence_count": lexical_occurrence_counts[identity],
            "exact_surface_count": len(lexical_surface_sets[identity]),
            "member_surfaces": sorted(lexical_surface_sets[identity]),
        })

    lexical_frequency.sort(
        key=lambda x: (-x["occurrence_count"], x["lexical_identity_arabic"])
    )

    write_json(out_dir / "audit_result.json", {
        "status": "VALIDATED_RECOVERED",
        "correction_count": len(corrections),
        "corrections": corrections,
        "validation_findings": [],
        "usage": usage,
        "recovered_without_api_call": True,
    })

    write_json(out_dir / "surface_to_lexeme_map_reviewed.json", {
        "version": "2.1-reviewed",
        "surface_count": len(reviewed_mappings),
        "lexical_identity_count": len(reviewed_groups),
        "mappings": reviewed_mappings,
    })

    write_json(out_dir / "lexical_groups_reviewed.json", {
        "version": "2.1-reviewed",
        "surface_count": len(reviewed_mappings),
        "lexical_identity_count": len(reviewed_groups),
        "groups": reviewed_groups,
    })

    write_json(out_dir / "descriptor_occurrences_lexical.json", {
        "version": "2.1-reviewed",
        "occurrence_count": len(enriched),
        "occurrences": enriched,
    })

    write_json(out_dir / "lexical_frequency.json", {
        "version": "2.1-reviewed",
        "lexical_identity_count": len(reviewed_groups),
        "total_occurrences": len(enriched),
        "lexical_identities": lexical_frequency,
    })

    print()
    print("RECOVERY STATUS: PASS")
    print(f"Recovered corrections: {len(corrections)}")
    print(f"Final lexical identities: {len(reviewed_groups)}")
    print(f"Occurrence records joined: {len(enriched)}")
    print("Additional API call made: NO")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    args = ap.parse_args()

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    out_dir = run_dir / "phase2_global_audit_sol_v1"

    raw_path = out_dir / "raw_response.json"
    result_path = out_dir / "audit_result.json"
    api_error_path = out_dir / "api_error.json"

    print("NAMES OF ALLAH — PHASE 2 GLOBAL AUDIT RECOVERY")
    print("================================================")
    print()

    if api_error_path.is_file():
        err = read_json(api_error_path)
        print("The API call failed.")
        print(f"Error type: {err.get('error_type')}")
        print(f"Error: {err.get('error_message')}")
        print("Additional API call made: NO")
        return 2

    if not raw_path.is_file():
        print(f"No saved raw response found: {raw_path}")
        print("Additional API call made: NO")
        return 2

    raw = read_json(raw_path)
    existing_result = read_json(result_path) if result_path.is_file() else {}

    print(f"Saved response ID: {raw.get('id')}")
    print(f"Response status: {raw.get('status')}")
    print(f"Existing audit status: {existing_result.get('status')}")
    print(f"Incomplete details: {raw.get('incomplete_details')}")
    print(f"Error field: {raw.get('error')}")
    print(f"Usage: {json.dumps(raw.get('usage'), ensure_ascii=False)}")

    refusals = collect_refusals(raw)
    if refusals:
        print()
        print("Refusal:")
        for refusal in refusals:
            print(refusal)

    pieces = collect_output_text(raw)
    text = "".join(pieces)

    print()
    print(f"Output-text pieces found: {len(pieces)}")
    print(f"Output-text characters found: {len(text)}")

    if not text:
        output_types = []

        def walk_types(x: Any):
            if isinstance(x, dict):
                if isinstance(x.get("type"), str):
                    output_types.append(x["type"])
                for v in x.values():
                    walk_types(v)
            elif isinstance(x, list):
                for v in x:
                    walk_types(v)

        walk_types(raw)
        print(f"Response content types: {sorted(set(output_types))}")
        print()
        print("There is no recoverable model answer in the saved response.")
        print("The previous runner exited silently here; that was a runner bug.")
        print("No additional API call was made.")
        return 3

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        recovery_text = out_dir / "recovered_output_text.txt"
        recovery_text.write_text(text, encoding="utf-8")
        print()
        print(f"Saved model text is not valid JSON: {exc}")
        print(f"Recovered text saved to: {recovery_text.relative_to(PROJECT_ROOT)}")
        print("No additional API call was made.")
        return 3

    corrections = parsed.get("corrections")
    if not isinstance(corrections, list):
        print()
        print("Recovered JSON has no corrections list.")
        print("No additional API call was made.")
        return 3

    print(f"Recovered correction rows: {len(corrections)}")

    finalize(
        run_dir=run_dir,
        out_dir=out_dir,
        corrections=corrections,
        usage=raw.get("usage"),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
