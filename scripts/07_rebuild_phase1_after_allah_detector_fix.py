#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QURAN_FILE = PROJECT_ROOT / "quran-simple-plain.json"
INTEGRITY_ADJUDICATIONS_FILE = (
    PROJECT_ROOT
    / "adjudications"
    / "phase1_integrity_semantic_adjudications_v1.json"
)

ARABIC_DIACRITIC_RE = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)

STRICT_ALLAH_TOKEN_BARE_RE = re.compile(
    r"^(?:و|ف)?(?:الله|بالله|لله|تالله|اللهم|آلله|أبالله)$"
)

STRICT_MODEL_ALLAH_SURFACE_RE = re.compile(
    r"^(?:اللَّه[َُِ]?|لِلَّه[َُِ]?|اللَّهُمَّ|آللَّه[َُِ]?)$"
)

EXPECTED_OLD_FALSE_POSITIVE_TOKENS = {
    ("6:39", "يُضْلِلْهُ"),
    ("62:11", "اللَّهْوِ"),
    ("77:31", "اللَّهَبِ"),
}


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


def strip_diacritics(text: str) -> str:
    return ARABIC_DIACRITIC_RE.sub("", text)


def strict_allah_source_token(token: str) -> bool:
    return bool(
        STRICT_ALLAH_TOKEN_BARE_RE.fullmatch(strip_diacritics(token))
    )


def model_allah_surface(value: str) -> bool:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        return False
    return strict_allah_source_token(value)


def broad_old_detector(token: str) -> bool:
    bare = strip_diacritics(token)
    return "الله" in bare or bare.endswith("لله")


def non_diacritic_index_map(text: str):
    chars = []
    idx_map = []
    for i, ch in enumerate(text):
        if ARABIC_DIACRITIC_RE.fullmatch(ch):
            continue
        chars.append(ch)
        idx_map.append(i)
    return "".join(chars), idx_map


def expected_allah_surfaces(source: str):
    out = []
    cursor = 0

    for token in source.split():
        token_start = source.find(token, cursor)
        if token_start < 0:
            raise RuntimeError(f"Could not resolve token in source: {token}")
        cursor = token_start + len(token)

        if not strict_allah_source_token(token):
            continue

        bare, idx_map = non_diacritic_index_map(token)

        # Interrogative hamza fused orthographically with Allah:
        # آللَّهُ. The plain proper-name spelling اللَّهُ is not a literal
        # contiguous substring of this Quran token, so preserve the whole
        # written surface under the Phase-1 exact-span policy.
        if bare == "آلله":
            out.append({
                "surface": token,
                "start": token_start,
                "source_token": token,
            })
            continue

        if "اللهم" in bare:
            idx = bare.find("اللهم")
        elif "الله" in bare:
            idx = bare.find("الله")
        elif "لله" in bare:
            idx = bare.find("لله")
        else:
            raise RuntimeError(f"Strict Allah token had no known core: {token}")

        start_orig = idx_map[idx]
        out.append({
            "surface": token[start_orig:],
            "start": token_start + start_orig,
            "source_token": token,
        })

    return out


def literal_positions(source: str, value: str):
    out = []
    pos = 0
    while True:
        i = source.find(value, pos)
        if i < 0:
            break
        out.append(i)
        pos = i + 1
    return out


def resolve_positions(source: str, values: list[str]):
    used = Counter()
    out = []
    for value in values:
        positions = literal_positions(source, value)
        n = used[value]
        if n >= len(positions):
            raise RuntimeError(
                f"Cannot resolve exact occurrence {value!r} in {source!r}"
            )
        out.append((positions[n], value))
        used[value] += 1
    return out


def reconcile_allah_strict(source: str, result: dict[str, Any]):
    new = copy.deepcopy(result)

    descriptors = new.get("descriptors")
    manual = new.get("manual_review")
    if not isinstance(descriptors, list) or not isinstance(manual, list):
        raise RuntimeError(f"Invalid Phase-1 result lists at {result.get('verse_key')}")

    expected = expected_allah_surfaces(source)
    expected_values = [x["surface"] for x in expected]

    model_allah = [x for x in descriptors if model_allah_surface(x)]
    model_manual_allah = [x for x in manual if model_allah_surface(x)]

    non_allah_descriptors = [
        x for x in descriptors if not model_allah_surface(x)
    ]
    non_allah_manual = [
        x for x in manual if not model_allah_surface(x)
    ]

    positioned = resolve_positions(source, non_allah_descriptors)
    positioned.extend((x["start"], x["surface"]) for x in expected)
    positioned.sort(key=lambda x: x[0])

    new["descriptors"] = [x[1] for x in positioned]
    new["manual_review"] = non_allah_manual

    repair = None
    if model_allah != expected_values or model_manual_allah:
        repair = {
            "code": "DETERMINISTIC_ALLAH_RECONCILIATION_V2",
            "verse_key": result.get("verse_key"),
            "model_allah_descriptors": model_allah,
            "model_allah_manual_review": model_manual_allah,
            "expected_allah_surfaces": expected_values,
            "source_tokens": [x["source_token"] for x in expected],
        }

    return new, repair


def build_quran_index(quran: dict[str, Any]):
    out = {}
    for surah in quran["surahs"]:
        s = surah["number"]
        for ayah in surah["ayahs"]:
            if ayah["number"] <= 0:
                continue
            key = f"{s}:{ayah['number']}"
            out[key] = ayah["text"]
    return out


def validate_list(source: str, values: Any, verse_key: str, field: str):
    findings = []
    if not isinstance(values, list):
        return [{"code": f"{field.upper()}_NOT_LIST", "verse_key": verse_key}]

    used = Counter()
    resolved = []

    for i, value in enumerate(values, 1):
        if not isinstance(value, str) or not value:
            findings.append({
                "code": f"{field.upper()}_INVALID_ITEM",
                "verse_key": verse_key,
                "item_index": i,
                "value": value,
            })
            continue

        positions = literal_positions(source, value)
        if not positions:
            findings.append({
                "code": f"{field.upper()}_NOT_EXACT_SUBSTRING",
                "verse_key": verse_key,
                "item_index": i,
                "value": value,
            })
            continue

        n = used[value]
        if n >= len(positions):
            findings.append({
                "code": f"{field.upper()}_DUPLICATE_EXCEEDS_SOURCE",
                "verse_key": verse_key,
                "item_index": i,
                "value": value,
            })
            continue

        resolved.append(positions[n])
        used[value] += 1

    if resolved != sorted(resolved):
        findings.append({
            "code": f"{field.upper()}_NOT_LEFT_TO_RIGHT",
            "verse_key": verse_key,
            "positions": resolved,
            "values": values,
        })

    return findings


def validate_result(source: str, result: dict[str, Any]):
    verse_key = result["verse_key"]
    findings = []
    findings.extend(validate_list(
        source, result.get("descriptors"), verse_key, "descriptors"
    ))
    findings.extend(validate_list(
        source, result.get("manual_review"), verse_key, "manual_review"
    ))

    expected = expected_allah_surfaces(source)
    returned = [
        x for x in result.get("descriptors", [])
        if model_allah_surface(x)
    ]
    if len(returned) != len(expected):
        findings.append({
            "code": "ALLAH_OCCURRENCE_COUNT_MISMATCH",
            "verse_key": verse_key,
            "expected": [x["surface"] for x in expected],
            "returned": returned,
        })

    return findings


def apply_manual_descriptor_adjudications(
    packet_id: str,
    verse_result: dict[str, Any],
    descriptor_rules: dict[str, dict[str, Any]],
    source: str,
):
    """
    Apply the eight already-frozen full-verse descriptor adjudications BEFORE
    strict Allah reconciliation.

    These adjudications were intentionally recorded as complete replacement
    arrays. Some exist precisely because the raw model returned a non-exact
    substring (for example 2:71 `رَبَّكَ`). Therefore requiring the raw array
    to be structurally valid before applying the adjudication is circular.

    Safety comes from:
    - exact verse_key match;
    - exact frozen Quran source_text match;
    - full-array replacement only;
    - ordinary exact-substring/order validation after replacement;
    - strict Allah reconciliation is still run afterward.
    """
    verse_key = verse_result["verse_key"]
    rule = descriptor_rules.get(verse_key)
    if rule is None:
        return verse_result, None

    if rule.get("operation") != "REPLACE_FULL_DESCRIPTOR_ARRAY":
        raise RuntimeError(
            f"Unsupported adjudication operation at {verse_key}: "
            f"{rule.get('operation')}"
        )

    if rule.get("source_text") != source:
        raise RuntimeError(
            f"Frozen Quran source mismatch for adjudication {verse_key}"
        )

    current = copy.deepcopy(verse_result.get("descriptors"))

    out = copy.deepcopy(verse_result)
    out["descriptors"] = copy.deepcopy(rule["final_descriptors"])
    out["manual_review"] = copy.deepcopy(rule["manual_review"])

    return out, {
        "packet_id": packet_id,
        "verse_key": verse_key,
        "raw_model_descriptors": current,
        "recorded_prior_descriptor_array": copy.deepcopy(
            rule.get("model_descriptors")
        ),
        "after": copy.deepcopy(out["descriptors"]),
        "reason_codes": copy.deepcopy(rule["reason_codes"]),
        "operation": rule["operation"],
    }


def apply_manual_review_decisions(
    verse_result: dict[str, Any],
    review_rules_by_verse: dict[str, list[dict[str, Any]]],
):
    verse_key = verse_result["verse_key"]
    rules = review_rules_by_verse.get(verse_key, [])
    if not rules:
        return verse_result, []

    out = copy.deepcopy(verse_result)
    applied = []

    for rule in rules:
        surface = rule["surface_arabic"]
        decision = rule["decision"]

        if decision == "EXCLUDE":
            if surface not in out["manual_review"]:
                raise RuntimeError(
                    f"Manual-review exclusion precondition failed at "
                    f"{verse_key}: {surface}"
                )
            out["manual_review"].remove(surface)
            applied.append({
                "verse_key": verse_key,
                "surface_arabic": surface,
                "decision": "EXCLUDE",
                "reason_code": rule["reason_code"],
            })
        elif decision == "INCLUDE":
            if surface not in out["manual_review"]:
                raise RuntimeError(
                    f"Manual-review inclusion precondition failed at "
                    f"{verse_key}: {surface}"
                )
            out["manual_review"].remove(surface)
            out["descriptors"].append(surface)
            out["descriptors"] = [
                value
                for _, value in sorted(
                    resolve_positions(
                        rule["verse_text"],
                        out["descriptors"],
                    ),
                    key=lambda x: x[0],
                )
            ]
            applied.append({
                "verse_key": verse_key,
                "surface_arabic": surface,
                "decision": "INCLUDE",
                "reason_code": rule["reason_code"],
            })
        else:
            raise RuntimeError(
                f"Unsupported manual-review decision: {decision}"
            )

    return out, applied



def apply_integrity_semantic_adjudications(
    verse_result: dict[str, Any],
    source: str,
    rules_by_verse: dict[str, list[dict[str, Any]]],
):
    verse_key = verse_result["verse_key"]
    rules = rules_by_verse.get(verse_key, [])
    if not rules:
        return verse_result, []

    out = copy.deepcopy(verse_result)
    applied = []

    for rule in rules:
        if rule["source_text"] != source:
            raise RuntimeError(
                f"Integrity adjudication source mismatch at {verse_key}"
            )

        surface = rule["surface_arabic"]
        decision = rule["decision"]

        if decision != "EXCLUDE":
            raise RuntimeError(
                f"Unsupported integrity adjudication decision: {decision}"
            )

        if surface not in out["descriptors"]:
            raise RuntimeError(
                f"Integrity adjudication precondition failed at "
                f"{verse_key}: descriptor {surface!r} not present"
            )

        out["descriptors"].remove(surface)
        applied.append({
            "verse_key": verse_key,
            "surface_arabic": surface,
            "decision": decision,
            "reason_code": rule["reason_code"],
        })

    return out, applied


def make_occurrence_outputs(
    out_dir: Path,
    run_name: str,
    quran_sha: str,
    quran_index: dict[str, str],
    resolved_files: list[Path],
):
    verse_seen = Counter()
    occurrences = []
    surface_counts = Counter()
    surface_locations = defaultdict(list)
    manual_review = []

    for path in resolved_files:
        attempt = load_json(path)
        packet_id = attempt["packet_id"]

        for vr in attempt["parsed_output"]["verse_results"]:
            verse_key = vr["verse_key"]
            source = quran_index[verse_key]
            verse_seen[verse_key] += 1

            for field, prefix in (("descriptors", "d"), ("manual_review", "m")):
                used = Counter()
                for ordinal, value in enumerate(vr[field], 1):
                    positions = literal_positions(source, value)
                    n = used[value]
                    if n >= len(positions):
                        raise RuntimeError(
                            f"Cannot position {verse_key} {field} {value}"
                        )
                    start = positions[n]
                    end = start + len(value)
                    used[value] += 1
                    oid = f"{verse_key}:{prefix}{ordinal:02d}"

                    row = {
                        "occurrence_id": oid,
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
                            "occurrence_id": oid,
                            "verse_key": verse_key,
                            "start_offset": start,
                            "end_offset": end,
                        })

    if len(verse_seen) != 6236:
        raise RuntimeError(
            f"Expected 6236 distinct numbered verses, found {len(verse_seen)}"
        )
    duplicates = [k for k, n in verse_seen.items() if n != 1]
    if duplicates:
        raise RuntimeError(
            f"Numbered verse coverage is not exactly once: {duplicates[:10]}"
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

    save_json(out_dir / "phase1_occurrence_ledger.json", {
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "occurrence_count": len(occurrences),
        "occurrences": occurrences,
    })
    save_json(out_dir / "exact_surface_inventory.json", {
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "descriptor_occurrences": len(occurrences),
        "distinct_exact_surfaces": len(inventory),
        "inventory": inventory,
    })
    save_json(out_dir / "manual_review_occurrences.json", {
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "manual_review_count": len(manual_review),
        "occurrences": manual_review,
    })

    return occurrences, inventory, manual_review


def build_phase2_model_input(
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

    norm_dir = prep_dir / "phase2_normalization_integrity_v1_4"
    norm_dir.mkdir(parents=True, exist_ok=False)

    save_json(norm_dir / "model_input.json", {
        "phase": "phase2_lexical_normalization_integrity_v1_4",
        "run_name": run_name,
        "quran_source_sha256": quran_sha,
        "surface_count": len(candidates),
        "candidates": candidates,
    })

    return candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    args = ap.parse_args()

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    attempts_dir = run_dir / "attempts"
    old_resolved_dir = run_dir / "resolved_attempts"
    descriptor_adj_path = run_dir / "manual_adjudications.json"
    review_adj_path = (
        run_dir / "phase2_preparation" / "manual_review_adjudications.json"
    )

    for path in (
        QURAN_FILE,
        attempts_dir,
        old_resolved_dir,
        descriptor_adj_path,
        review_adj_path,
        INTEGRITY_ADJUDICATIONS_FILE,
    ):
        if not path.exists():
            raise SystemExit(f"Missing required path: {path}")

    quran_sha = sha256_file(QURAN_FILE)
    quran = load_json(QURAN_FILE)
    quran_index = build_quran_index(quran)

    if len(quran_index) != 6236:
        raise SystemExit(
            f"Frozen Quran source must contain 6236 numbered verses; "
            f"found {len(quran_index)}"
        )

    # Prove the exact scope of the old broad detector against the frozen Quran.
    old_false_tokens = set()
    for verse_key, source in quran_index.items():
        for token in source.split():
            if broad_old_detector(token) and not strict_allah_source_token(token):
                old_false_tokens.add((verse_key, token))

    if old_false_tokens != EXPECTED_OLD_FALSE_POSITIVE_TOKENS:
        raise SystemExit(
            "Unexpected broad-vs-strict Allah detector scope.\n"
            f"Expected: {sorted(EXPECTED_OLD_FALSE_POSITIVE_TOKENS)}\n"
            f"Actual:   {sorted(old_false_tokens)}"
        )

    interrogative_expectations = {
        "10:59": ["اللَّهُ", "آللَّهُ", "اللَّهِ"],
        "27:59": ["لِلَّهِ", "آللَّهُ"],
    }
    for verse_key, expected in interrogative_expectations.items():
        actual = [
            x["surface"]
            for x in expected_allah_surfaces(quran_index[verse_key])
        ]
        if actual != expected:
            raise SystemExit(
                "Interrogative-Allah surface policy mismatch at "
                f"{verse_key}. Expected {expected}, got {actual}"
            )

    descriptor_adj = load_json(descriptor_adj_path)
    descriptor_rules = {
        x["verse_key"]: x
        for x in descriptor_adj["adjudications"]
    }

    review_adj = load_json(review_adj_path)
    review_rules_by_verse = defaultdict(list)
    for x in review_adj["decisions"]:
        review_rules_by_verse[x["verse_key"]].append(x)

    integrity_adj = load_json(INTEGRITY_ADJUDICATIONS_FILE)
    integrity_rules_by_verse = defaultdict(list)
    for x in integrity_adj["decisions"]:
        integrity_rules_by_verse[x["verse_key"]].append(x)

    attempt_files = sorted(attempts_dir.glob("*__attempt-1.json"))
    if len(attempt_files) != 190:
        raise SystemExit(
            f"Expected 190 original attempt files, found {len(attempt_files)}"
        )

    out_resolved = run_dir / "resolved_attempts_integrity_v1_4"
    out_resolution = run_dir / "resolution_integrity_v1_4"
    out_prep = run_dir / "phase2_preparation_integrity_v1_4"

    for path in (out_resolved, out_resolution, out_prep):
        if path.exists():
            raise SystemExit(
                f"Refusing to overwrite existing output: {path}"
            )

    out_resolved.mkdir(parents=True)
    out_resolution.mkdir(parents=True)
    out_prep.mkdir(parents=True)

    descriptor_adjudications_applied = []
    review_decisions_applied = []
    integrity_adjudications_applied = []
    strict_repairs = []
    validation_findings = []
    verse_seen = Counter()

    old_new_differences = []

    old_resolved_by_packet = {
        load_json(p)["packet_id"]: load_json(p)
        for p in sorted(old_resolved_dir.glob("*__attempt-1.json"))
    }

    for path in attempt_files:
        original = load_json(path)
        packet_id = original["packet_id"]

        raw_parsed = original.get("model_parsed_output")
        if not isinstance(raw_parsed, dict):
            raise SystemExit(
                f"Missing model_parsed_output in {path.name}"
            )

        rebuilt = copy.deepcopy(original)
        rebuilt_parsed = copy.deepcopy(raw_parsed)

        new_results = []
        for raw_vr in rebuilt_parsed["verse_results"]:
            verse_key = raw_vr["verse_key"]
            verse_seen[verse_key] += 1
            source = quran_index[verse_key]

            vr, applied = apply_manual_descriptor_adjudications(
                packet_id,
                raw_vr,
                descriptor_rules,
                source,
            )
            if applied:
                descriptor_adjudications_applied.append(applied)

            vr, repair = reconcile_allah_strict(source, vr)
            if repair:
                strict_repairs.append({
                    "packet_id": packet_id,
                    **repair,
                })

            vr, integrity_applied = apply_integrity_semantic_adjudications(
                vr,
                source,
                integrity_rules_by_verse,
            )
            integrity_adjudications_applied.extend(integrity_applied)

            vr, review_applied = apply_manual_review_decisions(
                vr,
                review_rules_by_verse,
            )
            review_decisions_applied.extend(review_applied)

            validation_findings.extend(
                validate_result(source, vr)
            )
            new_results.append(vr)

        rebuilt_parsed["verse_results"] = new_results
        rebuilt["parsed_output"] = rebuilt_parsed
        rebuilt["strict_allah_repairs_integrity_v1_4"] = [
            x for x in strict_repairs
            if x["packet_id"] == packet_id
        ]
        rebuilt["collection_status"] = "RESOLVED_INTEGRITY_V1_4_PENDING_GLOBAL_VALIDATION"

        old_packet = old_resolved_by_packet[packet_id]
        old_by_verse = {
            x["verse_key"]: x
            for x in old_packet["parsed_output"]["verse_results"]
        }

        for vr in new_results:
            ov = old_by_verse[vr["verse_key"]]
            if (
                ov.get("descriptors") != vr.get("descriptors")
                or ov.get("manual_review") != vr.get("manual_review")
            ):
                old_new_differences.append({
                    "packet_id": packet_id,
                    "verse_key": vr["verse_key"],
                    "old_descriptors": ov.get("descriptors"),
                    "new_descriptors": vr.get("descriptors"),
                    "old_manual_review": ov.get("manual_review"),
                    "new_manual_review": vr.get("manual_review"),
                })

        save_json(out_resolved / path.name, rebuilt)

    if len(verse_seen) != 6236 or any(n != 1 for n in verse_seen.values()):
        validation_findings.append({
            "code": "GLOBAL_VERSE_COVERAGE_FAILURE",
            "distinct_verses": len(verse_seen),
            "non_unit_counts": {
                k: n for k, n in verse_seen.items() if n != 1
            },
        })

    if len(descriptor_adjudications_applied) != 8:
        validation_findings.append({
            "code": "DESCRIPTOR_ADJUDICATION_COUNT_MISMATCH",
            "expected": 8,
            "actual": len(descriptor_adjudications_applied),
        })

    if len(review_decisions_applied) != 4:
        validation_findings.append({
            "code": "MANUAL_REVIEW_DECISION_COUNT_MISMATCH",
            "expected": 4,
            "actual": len(review_decisions_applied),
        })

    if len(integrity_adjudications_applied) != 2:
        validation_findings.append({
            "code": "INTEGRITY_SEMANTIC_ADJUDICATION_COUNT_MISMATCH",
            "expected": 2,
            "actual": len(integrity_adjudications_applied),
        })

    if validation_findings:
        report = {
            "status": "FAIL",
            "quran_source_sha256": quran_sha,
            "old_detector_false_positive_tokens": sorted(
                [
                    {"verse_key": k, "token": t}
                    for k, t in old_false_tokens
                ],
                key=lambda x: x["verse_key"],
            ),
            "validation_findings": validation_findings,
        }
        save_json(out_resolution / "rebuild_report.json", report)
        print("STATUS: FAIL")
        print(json.dumps(validation_findings, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    # Freeze statuses after successful global validation.
    resolved_files = sorted(out_resolved.glob("*__attempt-1.json"))
    for path in resolved_files:
        data = load_json(path)
        data["collection_status"] = "RESOLVED_INTEGRITY_V1_4_VALIDATED"
        save_json(path, data)

    occurrences, inventory, manual_review = make_occurrence_outputs(
        out_prep,
        args.run_name,
        quran_sha,
        quran_index,
        resolved_files,
    )

    old_ledger_path = (
        run_dir / "phase2_preparation" / "phase1_occurrence_ledger.json"
    )
    old_occurrences = load_json(old_ledger_path)["occurrences"]

    def occ_key(row):
        return (
            row["verse_key"],
            row["surface_arabic"],
            row["start_offset"],
            row["end_offset"],
        )

    old_counter = Counter(occ_key(x) for x in old_occurrences)
    new_counter = Counter(occ_key(x) for x in occurrences)

    removed_delta = set((old_counter - new_counter).elements())
    added_delta = set((new_counter - old_counter).elements())

    expected_removed_delta = {
        ("6:39", "لِلْهُ", 92, 98),
        ("10:59", "للَّهُ", 32, 38),
        ("27:59", "للَّهُ", 73, 79),
        ("62:11", "اللَّهْوِ", 119, 128),
        ("77:31", "اللَّهَبِ", 31, 40),
        ("92:12", "لَلْهُدَىٰ", 16, 26),
    }
    expected_added_delta = {
        ("10:59", "آللَّهُ", 103, 110),
        ("27:59", "آللَّهُ", 72, 79),
    }

    if removed_delta != expected_removed_delta:
        raise SystemExit(
            "Corrected ledger removed-delta mismatch.\n"
            f"Expected: {sorted(expected_removed_delta)}\n"
            f"Actual:   {sorted(removed_delta)}"
        )

    if added_delta != expected_added_delta:
        raise SystemExit(
            "Corrected ledger added-delta mismatch.\n"
            f"Expected: {sorted(expected_added_delta)}\n"
            f"Actual:   {sorted(added_delta)}"
        )

    for forbidden_verse, forbidden_surface in (
        ("48:10", "يَدُ اللَّهِ"),
        ("49:15", "بِاللَّهِ"),
    ):
        if any(
            x["verse_key"] == forbidden_verse
            and x["surface_arabic"] == forbidden_surface
            for x in occurrences
        ):
            raise SystemExit(
                f"Forbidden duplicate/semantic surface survived at "
                f"{forbidden_verse}: {forbidden_surface}"
            )

    candidates = build_phase2_model_input(
        out_prep,
        args.run_name,
        quran_sha,
        occurrences,
        inventory,
    )

    # The old detector bug must remove exactly these three generated descriptor
    # occurrences from the prior 5,121 ledger.  Manual-review exclusions do not
    # alter descriptor count.
    expected_descriptor_count = 5117
    expected_surface_count = 446

    if len(occurrences) != expected_descriptor_count:
        raise SystemExit(
            f"Expected corrected descriptor count {expected_descriptor_count}, "
            f"found {len(occurrences)}"
        )
    if len(inventory) != expected_surface_count:
        raise SystemExit(
            f"Expected corrected exact-surface count {expected_surface_count}, "
            f"found {len(inventory)}"
        )
    if manual_review:
        raise SystemExit(
            f"Expected 0 unresolved manual-review occurrences, found "
            f"{len(manual_review)}"
        )

    report = {
        "status": "PASS",
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "quran_source_modified": False,
        "original_attempts_modified": False,
        "old_resolved_attempts_modified": False,
        "old_phase2_outputs_modified": False,
        "old_detector_false_positive_tokens": [
            {"verse_key": k, "token": t}
            for k, t in sorted(old_false_tokens)
        ],
        "descriptor_adjudications_applied": len(
            descriptor_adjudications_applied
        ),
        "manual_review_decisions_applied": len(
            review_decisions_applied
        ),
        "integrity_semantic_adjudications_applied": len(
            integrity_adjudications_applied
        ),
        "old_vs_corrected_removed_occurrences": [
            {
                "verse_key": x[0],
                "surface_arabic": x[1],
                "start_offset": x[2],
                "end_offset": x[3],
            }
            for x in sorted(
                removed_delta,
                key=lambda y: (tuple(map(int, y[0].split(":"))), y[2], y[1]),
            )
        ],
        "old_vs_corrected_added_occurrences": [
            {
                "verse_key": x[0],
                "surface_arabic": x[1],
                "start_offset": x[2],
                "end_offset": x[3],
            }
            for x in sorted(
                added_delta,
                key=lambda y: (tuple(map(int, y[0].split(":"))), y[2], y[1]),
            )
        ],
        "old_vs_new_changed_verses": old_new_differences,
        "descriptor_occurrences_integrity_v1": len(occurrences),
        "distinct_exact_surfaces_integrity_v1": len(inventory),
        "manual_review_unresolved_integrity_v1": len(manual_review),
        "phase2_model_input_surfaces_integrity_v1": len(candidates),
        "outputs": {
            "resolved_attempts_integrity_v1": str(
                out_resolved.relative_to(PROJECT_ROOT)
            ),
            "resolution_integrity_v1": str(
                out_resolution.relative_to(PROJECT_ROOT)
            ),
            "phase2_preparation_integrity_v1": str(
                out_prep.relative_to(PROJECT_ROOT)
            ),
        },
    }
    save_json(out_resolution / "rebuild_report.json", report)

    print("NAMES OF ALLAH — ALLAH DETECTOR INTEGRITY REBUILD")
    print("===================================================")
    print()
    print("Status: PASS")
    print(f"Run: {args.run_name}")
    print(f"Quran SHA-256: {quran_sha}")
    print("Quran source modified: NO")
    print("Original attempts modified: NO")
    print("Old resolved attempts modified: NO")
    print("Old Phase-2 outputs modified: NO")
    print()
    print("Old-detector false positives:")
    for k, t in sorted(old_false_tokens):
        print(f"  {k:>6}  {t}")
    print()
    print(f"Descriptor occurrences corrected: {len(occurrences)}")
    print(f"Distinct exact surfaces corrected: {len(inventory)}")
    print(f"Manual-review unresolved corrected: {len(manual_review)}")
    print(f"Phase-2 input surfaces corrected: {len(candidates)}")
    print(f"Changed verses vs old resolved set: {len(old_new_differences)}")
    print()
    print(
        "Resolved corrected: "
        + str(out_resolved.relative_to(PROJECT_ROOT))
    )
    print(
        "Phase-2 prep corrected: "
        + str(out_prep.relative_to(PROJECT_ROOT))
    )
    print(
        "Report: "
        + str(
            (out_resolution / "rebuild_report.json")
            .relative_to(PROJECT_ROOT)
        )
    )


if __name__ == "__main__":
    main()
