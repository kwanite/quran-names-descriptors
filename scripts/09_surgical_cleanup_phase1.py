#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QURAN_FILE = PROJECT_ROOT / "quran-simple-plain.json"


PATCHES = {
    "6:39": {"op": "remove", "old": "لِلْهُ"},
    "10:59": {"op": "replace", "old": "للَّهُ", "new": "آللَّهُ"},
    "27:59": {"op": "replace", "old": "للَّهُ", "new": "آللَّهُ"},
    "62:11": {"op": "remove", "old": "اللَّهْوِ"},
    "77:31": {"op": "remove", "old": "اللَّهَبِ"},
    "92:12": {"op": "remove", "old": "لَلْهُدَىٰ"},
}

EXPECTED_DESCRIPTOR_OCCURRENCES = 5117
EXPECTED_DISTINCT_SURFACES = 446
EXPECTED_NUMBERED_VERSES = 6236
EXPECTED_ATTEMPT_FILES = 190


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_quran_index(quran: dict[str, Any]) -> dict[str, str]:
    out = {}
    for surah in quran["surahs"]:
        s = surah["number"]
        for ayah in surah["ayahs"]:
            if ayah["number"] > 0:
                out[f"{s}:{ayah['number']}"] = ayah["text"]
    return out


def literal_positions(source: str, value: str) -> list[int]:
    positions = []
    start = 0
    while True:
        i = source.find(value, start)
        if i < 0:
            break
        positions.append(i)
        start = i + 1
    return positions


def resolve_positions(source: str, values: list[str]) -> list[tuple[int, str]]:
    used = Counter()
    resolved = []

    for value in values:
        positions = literal_positions(source, value)
        if not positions:
            raise RuntimeError(
                f"Not an exact Quran substring: {value!r} in {source!r}"
            )

        n = used[value]
        if n >= len(positions):
            raise RuntimeError(
                f"Returned occurrence count exceeds Quran occurrence count: "
                f"{value!r} in {source!r}"
            )

        resolved.append((positions[n], value))
        used[value] += 1

    return resolved


def validate_values(source: str, values: list[str], verse_key: str, field: str):
    resolved = resolve_positions(source, values)
    starts = [x[0] for x in resolved]
    if starts != sorted(starts):
        raise RuntimeError(
            f"{field} not left-to-right at {verse_key}: {values}"
        )


def apply_patch(
    verse_key: str,
    descriptors: list[str],
) -> tuple[list[str], dict[str, Any] | None]:
    rule = PATCHES.get(verse_key)
    if not rule:
        return descriptors, None

    before = copy.deepcopy(descriptors)
    old = rule["old"]

    if before.count(old) != 1:
        raise RuntimeError(
            f"Patch precondition failed at {verse_key}: expected exactly one "
            f"{old!r}, found {before.count(old)} in {before}"
        )

    after = copy.deepcopy(before)
    idx = after.index(old)

    if rule["op"] == "remove":
        after.pop(idx)
    elif rule["op"] == "replace":
        after[idx] = rule["new"]
    else:
        raise RuntimeError(f"Unsupported patch operation: {rule['op']}")

    return after, {
        "verse_key": verse_key,
        "operation": rule["op"],
        "before": before,
        "after": after,
        "old_surface": old,
        "new_surface": rule.get("new"),
    }


def build_outputs(
    prep_dir: Path,
    run_name: str,
    quran_sha: str,
    quran_index: dict[str, str],
    resolved_files: list[Path],
):
    occurrences = []
    manual_review = []
    verse_seen = Counter()
    surface_counts = Counter()
    surface_locations = defaultdict(list)

    for path in resolved_files:
        attempt = load_json(path)
        packet_id = attempt["packet_id"]

        for vr in attempt["parsed_output"]["verse_results"]:
            verse_key = vr["verse_key"]
            source = quran_index[verse_key]
            verse_seen[verse_key] += 1

            validate_values(
                source,
                vr["descriptors"],
                verse_key,
                "descriptors",
            )
            validate_values(
                source,
                vr["manual_review"],
                verse_key,
                "manual_review",
            )

            for field, prefix in (("descriptors", "d"), ("manual_review", "m")):
                used = Counter()

                for ordinal, value in enumerate(vr[field], 1):
                    positions = literal_positions(source, value)
                    n = used[value]
                    start = positions[n]
                    used[value] += 1
                    end = start + len(value)

                    row = {
                        "occurrence_id": f"{verse_key}:{prefix}{ordinal:02d}",
                        "packet_id": packet_id,
                        "verse_key": verse_key,
                        "verse_text": source,
                        "surface_arabic": value,
                        "start_offset": start,
                        "end_offset": end,
                        "manual_review": field == "manual_review",
                    }

                    if field == "manual_review":
                        manual_review.append(row)
                    else:
                        occurrences.append(row)
                        surface_counts[value] += 1
                        surface_locations[value].append({
                            "occurrence_id": row["occurrence_id"],
                            "verse_key": verse_key,
                            "start_offset": start,
                            "end_offset": end,
                        })

    if len(verse_seen) != EXPECTED_NUMBERED_VERSES:
        raise RuntimeError(
            f"Expected {EXPECTED_NUMBERED_VERSES} numbered verses, "
            f"found {len(verse_seen)}"
        )

    bad_counts = {k: n for k, n in verse_seen.items() if n != 1}
    if bad_counts:
        raise RuntimeError(
            f"Numbered verses not represented exactly once: "
            f"{dict(list(bad_counts.items())[:10])}"
        )

    inventory = [
        {
            "surface_arabic": surface,
            "occurrence_count": count,
            "occurrences": surface_locations[surface],
        }
        for surface, count in sorted(
            surface_counts.items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
    ]

    save_json(prep_dir / "phase1_occurrence_ledger.json", {
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "occurrence_count": len(occurrences),
        "occurrences": occurrences,
    })

    save_json(prep_dir / "exact_surface_inventory.json", {
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "descriptor_occurrences": len(occurrences),
        "distinct_exact_surfaces": len(inventory),
        "inventory": inventory,
    })

    save_json(prep_dir / "manual_review_occurrences.json", {
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "manual_review_count": len(manual_review),
        "occurrences": manual_review,
    })

    return occurrences, inventory, manual_review


def build_phase2_input(
    prep_dir: Path,
    run_name: str,
    quran_sha: str,
    occurrences: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
):
    by_id = {x["occurrence_id"]: x for x in occurrences}
    candidates = []

    for item in inventory:
        examples = []
        seen_verses = set()

        for loc in item["occurrences"]:
            occ = by_id[loc["occurrence_id"]]
            if occ["verse_key"] in seen_verses:
                continue

            seen_verses.add(occ["verse_key"])
            examples.append({
                "occurrence_id": occ["occurrence_id"],
                "verse_key": occ["verse_key"],
                "verse_text": occ["verse_text"],
            })

            if len(examples) >= 2:
                break

        candidates.append({
            "surface_arabic": item["surface_arabic"],
            "occurrence_count": item["occurrence_count"],
            "representative_examples": examples,
        })

    norm_dir = prep_dir / "phase2_normalization_v1"
    norm_dir.mkdir(parents=True, exist_ok=False)

    save_json(norm_dir / "model_input.json", {
        "phase": "phase2_lexical_normalization_v1",
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "surface_count": len(candidates),
        "candidates": candidates,
    })


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Surgical cleanup of the frozen Phase-1 PASS outputs. "
            "No API call. No generalized Allah detector."
        )
    )
    ap.add_argument("--run-name", required=True)
    args = ap.parse_args()

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    source_dir = run_dir / "resolved_attempts"
    manual_adj_path = (
        run_dir
        / "phase2_preparation"
        / "manual_review_adjudications.json"
    )

    if not QURAN_FILE.is_file():
        raise SystemExit(f"Missing Quran source: {QURAN_FILE}")
    if not source_dir.is_dir():
        raise SystemExit(f"Missing frozen resolved attempts: {source_dir}")
    if not manual_adj_path.is_file():
        raise SystemExit(
            f"Missing manual-review adjudications: {manual_adj_path}"
        )

    out_resolved = run_dir / "resolved_attempts_clean_v1"
    out_resolution = run_dir / "resolution_clean_v1"
    out_prep = run_dir / "phase2_preparation_clean_v1"

    for path in (out_resolved, out_resolution, out_prep):
        if path.exists():
            raise SystemExit(
                f"Refusing to overwrite existing output: {path}"
            )

    out_resolved.mkdir(parents=True)
    out_resolution.mkdir(parents=True)
    out_prep.mkdir(parents=True)

    quran_sha = sha256_file(QURAN_FILE)
    quran_index = build_quran_index(load_json(QURAN_FILE))

    if len(quran_index) != EXPECTED_NUMBERED_VERSES:
        raise SystemExit(
            f"Frozen Quran source has {len(quran_index)} numbered verses; "
            f"expected {EXPECTED_NUMBERED_VERSES}"
        )

    review_adj = load_json(manual_adj_path)
    review_exclusions = defaultdict(list)
    for decision in review_adj["decisions"]:
        if decision["decision"] != "EXCLUDE":
            raise SystemExit(
                "This cleanup script expects the four frozen manual-review "
                "decisions to be exclusions."
            )
        review_exclusions[decision["verse_key"]].append(
            decision["surface_arabic"]
        )

    files = sorted(source_dir.glob("*__attempt-1.json"))
    if len(files) != EXPECTED_ATTEMPT_FILES:
        raise SystemExit(
            f"Expected {EXPECTED_ATTEMPT_FILES} frozen attempt files, "
            f"found {len(files)}"
        )

    patches_applied = []
    review_exclusions_applied = []
    patched_verse_seen = Counter()

    for path in files:
        data = load_json(path)
        out = copy.deepcopy(data)

        for vr in out["parsed_output"]["verse_results"]:
            verse_key = vr["verse_key"]
            source = quran_index[verse_key]

            new_desc, patch_record = apply_patch(
                verse_key,
                vr["descriptors"],
            )
            if patch_record:
                vr["descriptors"] = new_desc
                patches_applied.append(patch_record)
                patched_verse_seen[verse_key] += 1

            for surface in review_exclusions.get(verse_key, []):
                if surface not in vr["manual_review"]:
                    raise RuntimeError(
                        f"Manual-review exclusion precondition failed at "
                        f"{verse_key}: {surface!r}"
                    )
                vr["manual_review"].remove(surface)
                review_exclusions_applied.append({
                    "verse_key": verse_key,
                    "surface_arabic": surface,
                    "decision": "EXCLUDE",
                })

            validate_values(
                source,
                vr["descriptors"],
                verse_key,
                "descriptors",
            )
            validate_values(
                source,
                vr["manual_review"],
                verse_key,
                "manual_review",
            )

        out["collection_status"] = "CLEAN_V1_VALIDATED"
        out["surgical_cleanup_v1"] = {
            "source": "frozen resolved_attempts",
            "patches_applied_in_packet": [
                x for x in patches_applied
                if any(
                    y["verse_key"] == x["verse_key"]
                    for y in out["parsed_output"]["verse_results"]
                )
            ],
        }

        save_json(out_resolved / path.name, out)

    if set(patched_verse_seen) != set(PATCHES):
        raise SystemExit(
            f"Patch coverage mismatch. Expected {sorted(PATCHES)}, "
            f"got {sorted(patched_verse_seen)}"
        )

    if any(n != 1 for n in patched_verse_seen.values()):
        raise SystemExit(
            f"A patch verse was encountered more than once: "
            f"{dict(patched_verse_seen)}"
        )

    if len(patches_applied) != 6:
        raise SystemExit(
            f"Expected exactly 6 surgical verse patches, "
            f"applied {len(patches_applied)}"
        )

    if len(review_exclusions_applied) != 4:
        raise SystemExit(
            f"Expected exactly 4 manual-review exclusions, "
            f"applied {len(review_exclusions_applied)}"
        )

    resolved_files = sorted(out_resolved.glob("*__attempt-1.json"))

    occurrences, inventory, manual_review = build_outputs(
        out_prep,
        args.run_name,
        quran_sha,
        quran_index,
        resolved_files,
    )

    if len(occurrences) != EXPECTED_DESCRIPTOR_OCCURRENCES:
        raise SystemExit(
            f"Expected {EXPECTED_DESCRIPTOR_OCCURRENCES} descriptors, "
            f"found {len(occurrences)}"
        )

    if len(inventory) != EXPECTED_DISTINCT_SURFACES:
        raise SystemExit(
            f"Expected {EXPECTED_DISTINCT_SURFACES} exact surfaces, "
            f"found {len(inventory)}"
        )

    if manual_review:
        raise SystemExit(
            f"Expected 0 unresolved manual-review occurrences, "
            f"found {len(manual_review)}"
        )

    build_phase2_input(
        out_prep,
        args.run_name,
        quran_sha,
        occurrences,
        inventory,
    )

    report = {
        "status": "PASS",
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "quran_source_modified": False,
        "source_resolved_attempts_modified": False,
        "api_call_made": False,
        "surgical_patches_applied": patches_applied,
        "manual_review_exclusions_applied": review_exclusions_applied,
        "descriptor_occurrences": len(occurrences),
        "distinct_exact_surfaces": len(inventory),
        "manual_review_unresolved": len(manual_review),
        "phase2_input_surfaces": len(inventory),
        "outputs": {
            "resolved_attempts": str(
                out_resolved.relative_to(PROJECT_ROOT)
            ),
            "resolution": str(
                out_resolution.relative_to(PROJECT_ROOT)
            ),
            "phase2_preparation": str(
                out_prep.relative_to(PROJECT_ROOT)
            ),
        },
    }

    save_json(out_resolution / "clean_v1_report.json", report)

    print("NAMES OF ALLAH — PHASE 1 SURGICAL CLEANUP")
    print("==========================================")
    print()
    print("Status: PASS")
    print(f"Run: {args.run_name}")
    print(f"Quran SHA-256: {quran_sha}")
    print("Quran source modified: NO")
    print("Frozen resolved attempts modified: NO")
    print("API call made: NO")
    print()
    print(f"Surgical verse patches: {len(patches_applied)}")
    print(f"Manual-review exclusions: {len(review_exclusions_applied)}")
    print(f"Descriptor occurrences: {len(occurrences)}")
    print(f"Distinct exact surfaces: {len(inventory)}")
    print(f"Manual-review unresolved: {len(manual_review)}")
    print(f"Phase-2 input surfaces: {len(inventory)}")
    print()
    print(
        "Clean Phase-2 input: "
        + str(
            (
                out_prep
                / "phase2_normalization_v1"
                / "model_input.json"
            ).relative_to(PROJECT_ROOT)
        )
    )
    print(
        "Report: "
        + str(
            (out_resolution / "clean_v1_report.json")
            .relative_to(PROJECT_ROOT)
        )
    )


if __name__ == "__main__":
    main()
