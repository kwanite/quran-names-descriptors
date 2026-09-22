#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path


EXPECTED_SOURCE = {
    "lexical_identities": 233,
    "occurrences": 5067,
    "exact_surfaces": 415,
}

EXPECTED_RESULT = {
    "lexical_identities": 225,
    "occurrences": 5037,
}

VERSION = "semantic-exclusions-v2"
RUN_NAME = "phase1_full_v3_2_1_semantic_exclusions_v2"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_in_order(values):
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def exact_unique_substring_offset(text: str, needle: str) -> tuple[int, int]:
    first = text.find(needle)
    if first < 0:
        raise SystemExit(f"Replacement phrase is not an exact substring:\n{needle}\nIN:\n{text}")
    second = text.find(needle, first + 1)
    if second >= 0:
        raise SystemExit(
            f"Replacement phrase is not unique in verse; refusing to guess:\n{needle}\nIN:\n{text}"
        )
    return first, first + len(needle)


def main():
    ap = argparse.ArgumentParser(
        description="Build semantic_exclusions_v2 deterministically from semantic_exclusions_v1 + accepted manual review decisions."
    )
    ap.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Intentionally regenerate semantic_exclusions_v2 if it already exists.",
    )
    args = ap.parse_args()

    repo = args.repo.resolve()
    src = repo / "runs/phase1_full_v3_2_1/semantic_exclusions_v1"
    audit = repo / "runs/phase1_full_v3_2_1/semantic_precision_recall_audit_v1"
    decisions_path = audit / "manual_review_decisions_v1_reconciled.json"
    out = repo / "runs/phase1_full_v3_2_1/semantic_exclusions_v2"

    if out.exists() and any(out.iterdir()) and not args.overwrite:
        raise SystemExit(
            f"Output already exists: {out}\n"
            "Refusing to overwrite. Use --overwrite only for intentional deterministic regeneration."
        )

    paths = {
        "surface_map": src / "surface_to_lexeme_map_reviewed.json",
        "groups": src / "lexical_groups_reviewed.json",
        "occurrences": src / "descriptor_occurrences_lexical.json",
        "frequency": src / "lexical_frequency.json",
        "excluded_descriptors": src / "excluded_descriptors.json",
        "excluded_occurrences": src / "excluded_occurrences.json",
        "manifest": src / "semantic_exclusions_manifest.json",
        "decisions": decisions_path,
    }
    for name, path in paths.items():
        if not path.exists():
            raise SystemExit(f"Missing required {name}: {path}")

    sm = load(paths["surface_map"])
    gd = load(paths["groups"])
    od = load(paths["occurrences"])
    fd = load(paths["frequency"])
    prev_exd = load(paths["excluded_descriptors"])
    prev_exo = load(paths["excluded_occurrences"])
    prev_manifest = load(paths["manifest"])
    decisions = load(decisions_path)

    source_counts = {
        "lexical_identities": fd.get("lexical_identity_count", len(fd["lexical_identities"])),
        "occurrences": od.get("occurrence_count", len(od["occurrences"])),
        "exact_surfaces": sm.get("surface_count", len(sm["mappings"])),
    }
    if source_counts != EXPECTED_SOURCE:
        raise SystemExit(
            f"Source count mismatch.\nExpected: {EXPECTED_SOURCE}\nActual:   {source_counts}"
        )

    if decisions.get("status") != "RECONCILED_READY_FOR_BUILD":
        raise SystemExit(
            f"Decision ledger is not build-ready: status={decisions.get('status')!r}"
        )

    dsrc = decisions.get("source_counts", {})
    expected_dsrc = {
        "lexical_identities": EXPECTED_SOURCE["lexical_identities"],
        "numbered_occurrences": EXPECTED_SOURCE["occurrences"],
        "exact_surfaces": EXPECTED_SOURCE["exact_surfaces"],
    }
    if dsrc != expected_dsrc:
        raise SystemExit(
            f"Decision-ledger source counts mismatch.\nExpected: {expected_dsrc}\nActual:   {dsrc}"
        )

    source_occurrences = od["occurrences"]
    by_occurrence_id = {}
    for row in source_occurrences:
        oid = row["occurrence_id"]
        if oid in by_occurrence_id:
            raise SystemExit(f"Duplicate source occurrence_id: {oid}")
        by_occurrence_id[oid] = row

    source_identities = [x["lexical_identity_arabic"] for x in fd["lexical_identities"]]
    source_identity_set = set(source_identities)

    # ------------------------------------------------------------------
    # 1. Validate identity-level exclusions.
    # ------------------------------------------------------------------
    identity_exclusions = decisions["identity_exclusions_accepted"]
    excluded_identities = set()
    new_descriptor_records = []
    identity_excluded_occurrence_ids = set()

    for i, decision in enumerate(identity_exclusions, 1):
        ident = decision["lexical_identity_arabic"]
        expected_ids = decision["occurrence_ids"]

        if ident not in source_identity_set:
            raise SystemExit(f"Identity exclusion not found in v1: {ident}")
        if ident in excluded_identities:
            raise SystemExit(f"Duplicate identity exclusion in decision ledger: {ident}")

        actual_rows = [r for r in source_occurrences if r["lexical_identity_arabic"] == ident]
        actual_ids = [r["occurrence_id"] for r in actual_rows]
        if actual_ids != expected_ids:
            raise SystemExit(
                f"Occurrence list mismatch for identity exclusion {ident}\n"
                f"Expected: {expected_ids}\nActual:   {actual_ids}"
            )

        excluded_identities.add(ident)
        identity_excluded_occurrence_ids.update(actual_ids)

        member_surfaces = unique_in_order(r["surface_arabic"] for r in actual_rows)
        record = {
            "decision_id": f"SEMEX-V2-{i:03d}",
            "lexical_identity_arabic": ident,
            "category": decision["reason_code"],
            "decision": "EXCLUDE",
            "rationale": decision["reason_code"],
            "occurrence_count": len(actual_rows),
            "exact_surface_count": len(member_surfaces),
            "member_surfaces": member_surfaces,
            "verse_keys": [r["verse_key"] for r in actual_rows],
            "occurrence_ids": actual_ids,
            "source": "manual_review_decisions_v1_reconciled.json",
        }
        new_descriptor_records.append(record)

    # ------------------------------------------------------------------
    # 2. Validate occurrence-level exclusions (currently Ilah cleanup).
    # ------------------------------------------------------------------
    occurrence_exclusion_decisions = decisions["occurrence_exclusions_accepted"]
    occurrence_excluded_ids = set()
    occurrence_exclusion_records = []
    newly_excluded_occurrence_rows = []

    for i, decision in enumerate(occurrence_exclusion_decisions, 1):
        ident = decision["lexical_identity_arabic"]
        ids = decision["occurrence_ids"]
        decision_id = f"SEMOCC-V2-{i:03d}"

        for oid in ids:
            if oid not in by_occurrence_id:
                raise SystemExit(f"Occurrence exclusion ID not found: {oid}")
            row = by_occurrence_id[oid]
            if row["lexical_identity_arabic"] != ident:
                raise SystemExit(
                    f"Occurrence exclusion identity mismatch for {oid}: "
                    f"expected {ident}, actual {row['lexical_identity_arabic']}"
                )
            if oid in identity_excluded_occurrence_ids:
                raise SystemExit(f"Occurrence {oid} is excluded twice.")
            if oid in occurrence_excluded_ids:
                raise SystemExit(f"Duplicate occurrence exclusion: {oid}")

            occurrence_excluded_ids.add(oid)
            enriched = deepcopy(row)
            enriched.update({
                "semantic_exclusion_decision_id": decision_id,
                "semantic_exclusion_category": decision["reason_code"],
                "semantic_exclusion_rationale": decision["reason_code"],
                "semantic_exclusion_scope": "occurrence",
            })
            newly_excluded_occurrence_rows.append(enriched)

        original_count = sum(
            1 for r in source_occurrences
            if r["lexical_identity_arabic"] == ident
        )
        retained_after = original_count - len(ids)

        if original_count != decision["source_occurrence_count"]:
            raise SystemExit(
                f"Occurrence-level source count mismatch for {ident}: "
                f"ledger={decision['source_occurrence_count']} actual={original_count}"
            )
        if retained_after != decision["retained_occurrence_count_after_change"]:
            raise SystemExit(
                f"Occurrence-level retained count mismatch for {ident}: "
                f"ledger={decision['retained_occurrence_count_after_change']} actual={retained_after}"
            )

        occurrence_exclusion_records.append({
            "decision_id": decision_id,
            "lexical_identity_arabic": ident,
            "decision": "EXCLUDE_OCCURRENCES",
            "reason_code": decision["reason_code"],
            "occurrence_count": len(ids),
            "occurrence_ids": ids,
            "retain_identity": decision["retain_identity"],
            "source_occurrence_count": original_count,
            "retained_occurrence_count": retained_after,
        })

    # ------------------------------------------------------------------
    # 3. Filter the occurrence ledger.
    # ------------------------------------------------------------------
    removed_ids = identity_excluded_occurrence_ids | occurrence_excluded_ids
    transformed_occurrences = [
        deepcopy(r)
        for r in source_occurrences
        if r["occurrence_id"] not in removed_ids
    ]

    transformed_by_id = {r["occurrence_id"]: r for r in transformed_occurrences}

    # ------------------------------------------------------------------
    # 4. Apply exact phrase-boundary replacements.
    #    These are 1:1 identity replacements, not duplicate identities.
    # ------------------------------------------------------------------
    replacement_records = []
    replacement_old_to_new = {}

    for i, decision in enumerate(decisions["phrase_boundary_replacements_accepted"], 1):
        oid = decision["occurrence_id"]
        old_ident = decision["old_lexical_identity_arabic"]
        new_ident = decision["new_lexical_identity_arabic"]
        old_surface = decision["old_surface_arabic"]
        new_surface = decision["new_surface_arabic"]

        if oid not in transformed_by_id:
            raise SystemExit(f"Replacement occurrence missing after exclusions: {oid}")
        row = transformed_by_id[oid]

        if row["lexical_identity_arabic"] != old_ident:
            raise SystemExit(
                f"Replacement identity mismatch for {oid}: "
                f"expected {old_ident}, actual {row['lexical_identity_arabic']}"
            )
        if row["surface_arabic"] != old_surface:
            raise SystemExit(
                f"Replacement surface mismatch for {oid}: "
                f"expected {old_surface}, actual {row['surface_arabic']}"
            )
        if old_ident in replacement_old_to_new:
            raise SystemExit(f"Duplicate replacement of identity: {old_ident}")
        if new_ident in source_identity_set and new_ident != old_ident:
            raise SystemExit(
                f"Replacement would collide with an existing v1 identity: {new_ident}"
            )

        start, end = exact_unique_substring_offset(row["verse_text"], new_surface)

        # Verify the original shorter surface is contained inside the longer phrase.
        if old_surface not in new_surface:
            raise SystemExit(
                f"Replacement is not a phrase-boundary expansion:\n"
                f"{old_surface} -> {new_surface}"
            )

        row["lexical_identity_arabic"] = new_ident
        row["surface_arabic"] = new_surface
        row["start_offset"] = start
        row["end_offset"] = end
        row["semantic_revision"] = {
            "decision_id": f"SEMREP-V2-{i:03d}",
            "type": "PHRASE_BOUNDARY_EXPANSION",
            "old_lexical_identity_arabic": old_ident,
            "old_surface_arabic": old_surface,
        }

        replacement_old_to_new[old_ident] = new_ident
        replacement_records.append({
            "decision_id": f"SEMREP-V2-{i:03d}",
            **decision,
            "computed_start_offset": start,
            "computed_end_offset": end,
            "validated_exact_quran_substring": True,
        })

    # ------------------------------------------------------------------
    # 5. Rebuild identity order, frequencies, groups, and surface mappings
    #    from the transformed occurrence ledger.
    # ------------------------------------------------------------------
    result_identity_order = []
    for ident in source_identities:
        if ident in excluded_identities:
            continue
        ident2 = replacement_old_to_new.get(ident, ident)
        if ident2 not in result_identity_order:
            result_identity_order.append(ident2)

    rows_by_identity = defaultdict(list)
    for row in transformed_occurrences:
        rows_by_identity[row["lexical_identity_arabic"]].append(row)

    result_identity_set = set(rows_by_identity)
    if result_identity_set != set(result_identity_order):
        missing_from_order = sorted(result_identity_set - set(result_identity_order))
        empty_in_order = sorted(set(result_identity_order) - result_identity_set)
        raise SystemExit(
            f"Identity-order reconciliation failed.\n"
            f"Missing from order: {missing_from_order}\n"
            f"Empty in order: {empty_in_order}"
        )

    groups = []
    frequency = []
    for ident in result_identity_order:
        rows = rows_by_identity[ident]
        surfaces = unique_in_order(r["surface_arabic"] for r in rows)
        groups.append({
            "lexical_identity_arabic": ident,
            "member_surfaces": surfaces,
        })
        frequency.append({
            "lexical_identity_arabic": ident,
            "occurrence_count": len(rows),
            "exact_surface_count": len(surfaces),
            "member_surfaces": surfaces,
        })

    # Preserve original surface-map ordering where a pair is still present.
    actual_pairs = unique_in_order(
        (r["surface_arabic"], r["lexical_identity_arabic"])
        for r in transformed_occurrences
    )
    pair_set = set(actual_pairs)

    # Exact-surface map is expected to remain functional: one surface -> one identity.
    identities_by_surface = defaultdict(set)
    for surface, ident in actual_pairs:
        identities_by_surface[surface].add(ident)
    ambiguous_surfaces = {
        surface: sorted(idents)
        for surface, idents in identities_by_surface.items()
        if len(idents) != 1
    }
    if ambiguous_surfaces:
        raise SystemExit(
            "Exact surface now maps to multiple identities; refusing to build:\n"
            + json.dumps(ambiguous_surfaces, ensure_ascii=False, indent=2)
        )

    mappings = []
    seen_pairs = set()

    for old in sm["mappings"]:
        old_pair = (old["surface_arabic"], old["lexical_identity_arabic"])
        if old_pair in pair_set and old_pair not in seen_pairs:
            mappings.append({
                "surface_arabic": old_pair[0],
                "lexical_identity_arabic": old_pair[1],
            })
            seen_pairs.add(old_pair)

    for pair in actual_pairs:
        if pair not in seen_pairs:
            mappings.append({
                "surface_arabic": pair[0],
                "lexical_identity_arabic": pair[1],
            })
            seen_pairs.add(pair)

    if seen_pairs != pair_set:
        raise SystemExit("Surface-map reconstruction failed.")

    result_counts = {
        "lexical_identities": len(frequency),
        "occurrences": len(transformed_occurrences),
        "exact_surfaces": len(mappings),
    }

    for key, expected in EXPECTED_RESULT.items():
        if result_counts[key] != expected:
            raise SystemExit(
                f"Result {key} mismatch: expected {expected}, actual {result_counts[key]}"
            )

    # Strong internal consistency checks.
    if len({r["occurrence_id"] for r in transformed_occurrences}) != len(transformed_occurrences):
        raise SystemExit("Duplicate occurrence IDs in v2 output.")

    counter = Counter(r["lexical_identity_arabic"] for r in transformed_occurrences)
    for rec in frequency:
        if rec["occurrence_count"] != counter[rec["lexical_identity_arabic"]]:
            raise SystemExit(f"Frequency mismatch for {rec['lexical_identity_arabic']}")

    if len(groups) != len(frequency):
        raise SystemExit("Group/frequency identity count mismatch.")

    group_lookup = {g["lexical_identity_arabic"]: g["member_surfaces"] for g in groups}
    for rec in frequency:
        if rec["member_surfaces"] != group_lookup[rec["lexical_identity_arabic"]]:
            raise SystemExit(f"Group/frequency surface mismatch for {rec['lexical_identity_arabic']}")

    # Every output occurrence surface must be exact in its verse and match offsets.
    for row in transformed_occurrences:
        surface = row["surface_arabic"]
        verse = row["verse_text"]
        start = row["start_offset"]
        end = row["end_offset"]
        if verse[start:end] != surface:
            raise SystemExit(
                f"Offset/surface mismatch after build for {row['occurrence_id']}: "
                f"{verse[start:end]!r} != {surface!r}"
            )

    # ------------------------------------------------------------------
    # 6. Build cumulative exclusion history.
    # ------------------------------------------------------------------
    previous_descriptor_records = prev_exd.get("exclusions", [])
    cumulative_descriptor_records = previous_descriptor_records + new_descriptor_records

    previous_excluded_occurrences = prev_exo.get("occurrences", [])

    new_identity_excluded_rows = []
    decision_by_identity = {
        r["lexical_identity_arabic"]: r for r in new_descriptor_records
    }
    for oid in sorted(identity_excluded_occurrence_ids):
        row = deepcopy(by_occurrence_id[oid])
        rec = decision_by_identity[row["lexical_identity_arabic"]]
        row.update({
            "semantic_exclusion_decision_id": rec["decision_id"],
            "semantic_exclusion_category": rec["category"],
            "semantic_exclusion_rationale": rec["rationale"],
            "semantic_exclusion_scope": "identity",
        })
        new_identity_excluded_rows.append(row)

    new_excluded_occurrences = new_identity_excluded_rows + newly_excluded_occurrence_rows
    cumulative_excluded_occurrences = previous_excluded_occurrences + new_excluded_occurrences

    if len(new_excluded_occurrences) != 30:
        raise SystemExit(
            f"Expected 30 newly excluded occurrences, got {len(new_excluded_occurrences)}"
        )
    if len(cumulative_descriptor_records) != 30:
        raise SystemExit(
            f"Expected 30 cumulative excluded identities, got {len(cumulative_descriptor_records)}"
        )
    if len(cumulative_excluded_occurrences) != 80:
        raise SystemExit(
            f"Expected 80 cumulative excluded occurrences, got {len(cumulative_excluded_occurrences)}"
        )

    # ------------------------------------------------------------------
    # 7. Write outputs.
    # ------------------------------------------------------------------
    if out.exists():
        out.mkdir(parents=True, exist_ok=True)
    else:
        out.mkdir(parents=True)

    dump(out / "surface_to_lexeme_map_reviewed.json", {
        "version": VERSION,
        "source_version": sm["version"],
        "run_name": RUN_NAME,
        "semantic_exclusion_manifest": "semantic_exclusions_manifest.json",
        "surface_count": result_counts["exact_surfaces"],
        "lexical_identity_count": result_counts["lexical_identities"],
        "mappings": mappings,
    })

    dump(out / "lexical_groups_reviewed.json", {
        "version": VERSION,
        "source_version": gd["version"],
        "run_name": RUN_NAME,
        "semantic_exclusion_manifest": "semantic_exclusions_manifest.json",
        "surface_count": result_counts["exact_surfaces"],
        "lexical_identity_count": result_counts["lexical_identities"],
        "groups": groups,
    })

    dump(out / "descriptor_occurrences_lexical.json", {
        "version": VERSION,
        "source_version": od["version"],
        "run_name": RUN_NAME,
        "semantic_exclusion_manifest": "semantic_exclusions_manifest.json",
        "occurrence_count": result_counts["occurrences"],
        "occurrences": transformed_occurrences,
    })

    dump(out / "lexical_frequency.json", {
        "version": VERSION,
        "source_version": fd["version"],
        "run_name": RUN_NAME,
        "semantic_exclusion_manifest": "semantic_exclusions_manifest.json",
        "lexical_identity_count": result_counts["lexical_identities"],
        "total_occurrences": result_counts["occurrences"],
        "lexical_identities": frequency,
    })

    cumulative_excluded_surfaces = unique_in_order(
        r["surface_arabic"] for r in cumulative_excluded_occurrences
    )
    dump(out / "excluded_descriptors.json", {
        "version": VERSION,
        "parent_version": prev_exd.get("version"),
        "excluded_identity_count": len(cumulative_descriptor_records),
        "new_excluded_identity_count": len(new_descriptor_records),
        "cumulative_excluded_occurrence_count": len(cumulative_excluded_occurrences),
        "cumulative_excluded_occurrence_surface_count": len(cumulative_excluded_surfaces),
        "exclusions": cumulative_descriptor_records,
    })

    dump(out / "excluded_occurrences.json", {
        "version": VERSION,
        "parent_version": prev_exo.get("version"),
        "occurrence_count": len(cumulative_excluded_occurrences),
        "new_occurrence_count": len(new_excluded_occurrences),
        "occurrences": cumulative_excluded_occurrences,
    })

    dump(out / "occurrence_exclusions_v2.json", {
        "version": VERSION,
        "decision_count": len(occurrence_exclusion_records),
        "excluded_occurrence_count": len(occurrence_excluded_ids),
        "decisions": occurrence_exclusion_records,
    })

    dump(out / "phrase_boundary_replacements_v2.json", {
        "version": VERSION,
        "replacement_count": len(replacement_records),
        "replacements": replacement_records,
    })

    dump(out / "display_metadata_updates_pending.json", {
        "version": VERSION,
        "note": "Display-only updates accepted in manual review. These do not define semantic identity and are not applied to semantic corpus files by this builder.",
        "updates": decisions["translation_updates_accepted"],
    })

    manifest = {
        "version": VERSION,
        "date": "2026-09-22",
        "kind": "semantic_review_revision",
        "policy": {
            "phase2_files_modified": False,
            "semantic_exclusions_v1_modified": False,
            "operation": (
                "derive v2 from v1 by accepted identity exclusions, "
                "occurrence-level exclusions, and exact Quran-attested phrase-boundary replacements; "
                "then deterministically rebuild mappings/groups/frequencies"
            ),
            "display_metadata_kept_separate": True,
        },
        "source": {
            "authoritative_directory": str(src.relative_to(repo)),
            "parent_version": prev_manifest.get("version"),
            "input_counts": source_counts,
            "input_sha256": {
                name: sha256(path)
                for name, path in paths.items()
            },
        },
        "manual_review": {
            "decision_ledger": str(decisions_path.relative_to(repo)),
            "decision_ledger_sha256": sha256(decisions_path),
            "new_identity_exclusions": len(new_descriptor_records),
            "new_occurrence_exclusions": len(occurrence_excluded_ids),
            "phrase_boundary_replacements": len(replacement_records),
            "display_metadata_updates_pending": len(decisions["translation_updates_accepted"]),
        },
        "result": {
            "output_directory": str(out.relative_to(repo)),
            **result_counts,
        },
        "new_identity_exclusions": new_descriptor_records,
        "occurrence_exclusions": occurrence_exclusion_records,
        "phrase_boundary_replacements": replacement_records,
    }
    dump(out / "semantic_exclusions_manifest.json", manifest)

    with (out / "excluded_descriptors.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.writer(f)
        w.writerow([
            "decision_id",
            "arabic",
            "category",
            "decision",
            "occurrence_count",
            "exact_surface_count",
            "verse_keys",
            "rationale",
        ])
        for rec in cumulative_descriptor_records:
            w.writerow([
                rec.get("decision_id", ""),
                rec.get("lexical_identity_arabic", ""),
                rec.get("category", ""),
                rec.get("decision", "EXCLUDE"),
                rec.get("occurrence_count", ""),
                rec.get("exact_surface_count", ""),
                ", ".join(rec.get("verse_keys", [])),
                rec.get("rationale", ""),
            ])

    build_report = {
        "status": "PASS",
        "version": VERSION,
        "source_counts": source_counts,
        "result_counts": result_counts,
        "changes": {
            "new_identity_exclusions": len(new_descriptor_records),
            "new_identity_excluded_occurrences": len(identity_excluded_occurrence_ids),
            "new_occurrence_level_exclusions": len(occurrence_excluded_ids),
            "total_newly_removed_occurrences": len(new_excluded_occurrences),
            "phrase_boundary_replacements": len(replacement_records),
            "cumulative_excluded_identities": len(cumulative_descriptor_records),
            "cumulative_excluded_occurrences": len(cumulative_excluded_occurrences),
        },
        "validations": {
            "source_counts_match_frozen_v1": True,
            "decision_ledger_build_ready": True,
            "all_reviewed_occurrence_ids_exist": True,
            "all_reviewed_identities_match": True,
            "replacement_phrases_are_exact_unique_quran_substrings": True,
            "all_output_offsets_match_exact_surfaces": True,
            "no_duplicate_occurrence_ids": True,
            "surface_map_is_functional": True,
            "frequency_recomputed_from_occurrences": True,
            "groups_recomputed_from_occurrences": True,
            "semantic_exclusions_v1_untouched": True,
        },
        "pending_nonsemantic_work": {
            "display_metadata_updates": len(decisions["translation_updates_accepted"]),
            "viewer_repoint_and_root_form_rebuild": True,
        },
    }
    dump(out / "build_report.json", build_report)

    print("SEMANTIC EXCLUSIONS V2: PASS")
    print(
        f"{source_counts['lexical_identities']} -> "
        f"{result_counts['lexical_identities']} identities"
    )
    print(
        f"{source_counts['occurrences']} -> "
        f"{result_counts['occurrences']} occurrences"
    )
    print(
        f"{source_counts['exact_surfaces']} -> "
        f"{result_counts['exact_surfaces']} exact surfaces"
    )
    print(f"New identity exclusions: {len(new_descriptor_records)}")
    print(f"New occurrence-level exclusions: {len(occurrence_excluded_ids)}")
    print(f"Phrase-boundary replacements: {len(replacement_records)}")
    print(f"Output: {out}")


if __name__ == "__main__":
    main()
