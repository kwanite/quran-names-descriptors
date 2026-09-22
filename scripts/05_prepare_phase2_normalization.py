#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Prepare the global Phase-2 lexical-normalization input. No API call."
    )
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--examples-per-surface", type=int, default=2)
    args = ap.parse_args()

    if args.examples_per_surface < 1 or args.examples_per_surface > 3:
        raise SystemExit("--examples-per-surface must be between 1 and 3")

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    prep_dir = run_dir / "phase2_preparation"

    inventory_path = prep_dir / "exact_surface_inventory.json"
    ledger_path = prep_dir / "phase1_occurrence_ledger.json"
    manual_adj_path = prep_dir / "manual_review_adjudications.json"

    prompt_path = PROJECT_ROOT / "prompts" / "phase2_lexical_normalization_v1.md"
    schema_path = PROJECT_ROOT / "schemas" / "phase2_lexical_normalization_v1.schema.json"

    for path in (
        inventory_path,
        ledger_path,
        manual_adj_path,
        prompt_path,
        schema_path,
    ):
        if not path.is_file():
            raise SystemExit(f"Missing required file: {path}")

    inventory = load_json(inventory_path)
    ledger = load_json(ledger_path)
    manual_adj = load_json(manual_adj_path)

    if manual_adj.get("summary", {}).get("unresolved", None) != 0:
        raise SystemExit("Manual-review adjudications are not fully resolved")

    if inventory["quran_source_sha256"] != ledger["quran_source_sha256"]:
        raise SystemExit("Inventory/ledger Quran SHA mismatch")

    quran_sha = inventory["quran_source_sha256"]

    ledger_by_id = {
        row["occurrence_id"]: row
        for row in ledger["occurrences"]
    }

    candidates = []
    total_example_verses = 0

    for item in inventory["inventory"]:
        surface = item["surface_arabic"]
        count = item["occurrence_count"]
        locations = item["occurrences"]

        # Deterministic representative examples:
        # earliest occurrence(s) in Quran/ledger order, capped by user setting.
        examples = []
        seen_verses = set()
        for loc in locations:
            occ = ledger_by_id.get(loc["occurrence_id"])
            if not occ:
                raise SystemExit(
                    f"Occurrence missing from ledger: {loc['occurrence_id']}"
                )
            vk = occ["verse_key"]
            if vk in seen_verses:
                continue
            seen_verses.add(vk)
            examples.append({
                "occurrence_id": occ["occurrence_id"],
                "verse_key": vk,
                "verse_text": occ["verse_text"],
            })
            if len(examples) >= args.examples_per_surface:
                break

        total_example_verses += len(examples)
        candidates.append({
            "surface_arabic": surface,
            "occurrence_count": count,
            "representative_examples": examples,
        })

    if len(candidates) != inventory["distinct_exact_surfaces"]:
        raise SystemExit("Distinct-surface count mismatch")

    out_dir = prep_dir / "phase2_normalization_v1"
    if out_dir.exists():
        raise SystemExit(
            f"Refusing to overwrite existing output directory: {out_dir}"
        )
    out_dir.mkdir(parents=True)

    model_input = {
        "phase": "phase2_lexical_normalization_v1",
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "surface_count": len(candidates),
        "candidates": candidates,
    }
    input_path = out_dir / "model_input.json"
    save_json(input_path, model_input)

    # Also build a small diagnostic pilot containing difficult representative
    # forms. This is local-only and is not an API request.
    wanted = [
        "اللَّهُ",
        "اللَّهَ",
        "اللَّهِ",
        "لِلَّهِ",
        "رَبُّكَ",
        "رَبَّكَ",
        "رَبِّكَ",
        "رَبِّي",
        "رَبَّنَا",
        "رَبِّ الْعَالَمِينَ",
        "قَدِيرٌ",
        "قَادِرٍ",
        "جَاعِلٌ",
        "مُخْرِجٌ",
        "مَالِكِ يَوْمِ الدِّينِ"
    ]
    by_surface = {x["surface_arabic"]: x for x in candidates}
    pilot_candidates = [by_surface[x] for x in wanted if x in by_surface]
    pilot_path = out_dir / "pilot_model_input.json"
    save_json(pilot_path, {
        "phase": "phase2_lexical_normalization_v1_pilot",
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "surface_count": len(pilot_candidates),
        "candidates": pilot_candidates,
    })

    report = {
        "status": "PREPARED",
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "surface_count": len(candidates),
        "descriptor_occurrence_count": inventory["descriptor_occurrences"],
        "examples_per_surface": args.examples_per_surface,
        "representative_example_verses": total_example_verses,
        "manual_review_unresolved": 0,
        "model_input_bytes": input_path.stat().st_size,
        "pilot_surface_count": len(pilot_candidates),
        "pilot_input_bytes": pilot_path.stat().st_size,
        "prompt_sha256": sha256_file(prompt_path),
        "schema_sha256": sha256_file(schema_path),
        "model_input_sha256": sha256_file(input_path),
        "pilot_input_sha256": sha256_file(pilot_path),
        "api_call_made": False,
    }
    save_json(out_dir / "prepare_report.json", report)

    print("NAMES OF ALLAH — PHASE 2 NORMALIZATION PREPARE")
    print("================================================")
    print()
    print(f"Status: {report['status']}")
    print(f"Run: {args.run_name}")
    print(f"Exact surfaces: {report['surface_count']}")
    print(f"Descriptor occurrences represented: {report['descriptor_occurrence_count']}")
    print(f"Representative examples: {report['representative_example_verses']}")
    print(f"Manual-review unresolved: {report['manual_review_unresolved']}")
    print(f"Global model-input bytes: {report['model_input_bytes']}")
    print(f"Pilot surfaces: {report['pilot_surface_count']}")
    print(f"Pilot model-input bytes: {report['pilot_input_bytes']}")
    print()
    print(f"Prompt SHA-256: {report['prompt_sha256']}")
    print(f"Schema SHA-256: {report['schema_sha256']}")
    print(f"Model-input SHA-256: {report['model_input_sha256']}")
    print()
    print("NO API CALL WAS MADE.")


if __name__ == "__main__":
    main()
