#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QURAN_FILE = PROJECT_ROOT / "quran-simple-plain.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_quran_index(quran: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for surah in quran["surahs"]:
        s = surah["number"]
        for ayah in surah["ayahs"]:
            if ayah["number"] <= 0:
                continue
            key = f"{s}:{ayah['number']}"
            if key in out:
                raise RuntimeError(f"Duplicate Quran verse key: {key}")
            out[key] = ayah["text"]
    return out


def literal_positions(source: str, value: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        idx = source.find(value, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def validate_span_list(
    source: str,
    values: Any,
    *,
    verse_key: str,
    field_name: str,
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []

    if not isinstance(values, list):
        return [{
            "code": f"{field_name.upper()}_NOT_LIST",
            "verse_key": verse_key,
        }]

    used: Counter[str] = Counter()
    resolved_positions: list[int] = []

    for i, value in enumerate(values, 1):
        if not isinstance(value, str) or not value:
            problems.append({
                "code": f"{field_name.upper()}_INVALID_ITEM",
                "verse_key": verse_key,
                "item_index": i,
                "value": value,
            })
            continue

        positions = literal_positions(source, value)
        if not positions:
            problems.append({
                "code": f"{field_name.upper()}_NOT_EXACT_SUBSTRING",
                "verse_key": verse_key,
                "item_index": i,
                "value": value,
            })
            continue

        occurrence_number = used[value]
        if occurrence_number >= len(positions):
            problems.append({
                "code": f"{field_name.upper()}_DUPLICATE_EXCEEDS_SOURCE_OCCURRENCES",
                "verse_key": verse_key,
                "item_index": i,
                "value": value,
                "literal_occurrences_in_source": len(positions),
            })
            continue

        resolved_positions.append(positions[occurrence_number])
        used[value] += 1

    if len(resolved_positions) >= 2:
        if any(b < a for a, b in zip(resolved_positions, resolved_positions[1:])):
            problems.append({
                "code": f"{field_name.upper()}_NOT_IN_SOURCE_ORDER",
                "verse_key": verse_key,
                "values": values,
                "positions": resolved_positions,
            })

    return problems


def validate_verse_result(
    result: dict[str, Any],
    quran_index: dict[str, str],
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    verse_key = result.get("verse_key")

    if verse_key not in quran_index:
        return [{
            "code": "INVALID_VERSE_KEY",
            "verse_key": verse_key,
        }]

    source = quran_index[verse_key]

    problems.extend(validate_span_list(
        source,
        result.get("descriptors"),
        verse_key=verse_key,
        field_name="descriptors",
    ))
    problems.extend(validate_span_list(
        source,
        result.get("manual_review"),
        verse_key=verse_key,
        field_name="manual_review",
    ))

    descriptors = result.get("descriptors")
    manual = result.get("manual_review")
    if isinstance(descriptors, list) and isinstance(manual, list):
        overlap = sorted(set(descriptors).intersection(manual))
        if overlap:
            problems.append({
                "code": "SAME_VALUE_DESCRIPTOR_AND_MANUAL_REVIEW",
                "verse_key": verse_key,
                "values": overlap,
            })

    return problems


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Apply frozen Phase-1 adjudications without modifying original attempts or Quran text."
    )
    ap.add_argument("--run-name", required=True)
    ap.add_argument(
        "--adjudications",
        default=None,
        help="Defaults to runs/<run-name>/manual_adjudications.json",
    )
    args = ap.parse_args()

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    attempts_dir = run_dir / "attempts"
    if not attempts_dir.is_dir():
        raise SystemExit(f"Missing attempts directory: {attempts_dir}")

    adjudication_path = (
        Path(args.adjudications).expanduser().resolve()
        if args.adjudications
        else run_dir / "manual_adjudications.json"
    )
    if not adjudication_path.is_file():
        raise SystemExit(f"Missing adjudication file: {adjudication_path}")

    if not QURAN_FILE.is_file():
        raise SystemExit(f"Missing Quran source: {QURAN_FILE}")

    adjudication = load_json(adjudication_path)

    if adjudication.get("run_name") != args.run_name:
        raise SystemExit(
            f"Adjudication run mismatch: {adjudication.get('run_name')} != {args.run_name}"
        )

    expected_sha = adjudication["quran_source_sha256"]
    actual_sha = sha256_file(QURAN_FILE)
    if actual_sha != expected_sha:
        raise SystemExit(
            "QURAN SOURCE SHA-256 MISMATCH\n"
            f"Expected: {expected_sha}\n"
            f"Actual:   {actual_sha}\n"
            "Nothing was changed."
        )

    quran = load_json(QURAN_FILE)
    quran_index = build_quran_index(quran)
    if len(quran_index) != 6236:
        raise SystemExit(f"Expected 6236 numbered Quran verses, found {len(quran_index)}")

    adjudications = {
        item["verse_key"]: item
        for item in adjudication["adjudications"]
    }

    if len(adjudications) != len(adjudication["adjudications"]):
        raise SystemExit("Duplicate verse_key in adjudication file")

    resolved_dir = run_dir / "resolved_attempts"
    report_dir = run_dir / "resolution"
    if resolved_dir.exists():
        raise SystemExit(
            f"Refusing to overwrite existing resolved output: {resolved_dir}\n"
            "Remove or rename it manually if you intentionally want to rebuild."
        )

    resolved_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    attempt_files = sorted(attempts_dir.glob("*__attempt-1.json"))
    if len(attempt_files) != 190:
        raise SystemExit(f"Expected 190 attempt files, found {len(attempt_files)}")

    seen_verses: list[str] = []
    applied: list[dict[str, Any]] = []
    validation_findings: list[dict[str, Any]] = []
    packet_status_counts: Counter[str] = Counter()

    for src in attempt_files:
        original = load_json(src)
        resolved = copy.deepcopy(original)

        parsed = resolved.get("parsed_output")
        if not isinstance(parsed, dict):
            raise SystemExit(f"Missing parsed_output in {src.name}")

        verse_results = parsed.get("verse_results")
        if not isinstance(verse_results, list):
            raise SystemExit(f"Missing verse_results in {src.name}")

        changed_in_packet = 0

        for result in verse_results:
            verse_key = result.get("verse_key")
            seen_verses.append(verse_key)

            if verse_key in adjudications:
                rule = adjudications[verse_key]

                current = result.get("descriptors")
                expected_model = rule["model_descriptors"]
                if current != expected_model:
                    raise SystemExit(
                        "ADJUDICATION PRECONDITION FAILED\n"
                        f"Verse: {verse_key}\n"
                        f"Expected current descriptors: {expected_model}\n"
                        f"Actual current descriptors:   {current}\n"
                        "Nothing further was written."
                    )

                source_text = quran_index[verse_key]
                if source_text != rule["source_text"]:
                    raise SystemExit(
                        f"Quran source text mismatch for adjudication {verse_key}"
                    )

                result["descriptors"] = copy.deepcopy(rule["final_descriptors"])
                result["manual_review"] = copy.deepcopy(rule["manual_review"])
                changed_in_packet += 1

                applied.append({
                    "packet_id": resolved["packet_id"],
                    "verse_key": verse_key,
                    "before": current,
                    "after": rule["final_descriptors"],
                    "reason_codes": rule["reason_codes"],
                    "operation": rule["operation"],
                })

            validation_findings.extend(validate_verse_result(result, quran_index))

        resolved["original_collection_status"] = original.get("collection_status")
        resolved["resolution"] = {
            "adjudication_version": adjudication["adjudication_version"],
            "quran_source_sha256": actual_sha,
            "changed_verses_in_packet": changed_in_packet,
            "original_attempt_preserved": True,
            "source_attempt_file": f"attempts/{src.name}",
        }

        if changed_in_packet:
            resolved["collection_status"] = "ADJUDICATED_PENDING_GLOBAL_VALIDATION"
        else:
            resolved["collection_status"] = "UNCHANGED_PENDING_GLOBAL_VALIDATION"

        save_json(resolved_dir / src.name, resolved)
        packet_status_counts[resolved["collection_status"]] += 1

    # Every adjudication must have been applied exactly once.
    applied_counts = Counter(x["verse_key"] for x in applied)
    missing_adjudications = [
        k for k in adjudications if applied_counts[k] != 1
    ]
    if missing_adjudications:
        raise SystemExit(
            f"Adjudications not applied exactly once: {missing_adjudications}"
        )

    verse_counts = Counter(seen_verses)
    missing_core = sorted(set(quran_index) - set(verse_counts))
    duplicate_core = sorted(k for k, n in verse_counts.items() if n != 1)
    invalid_core = sorted(set(verse_counts) - set(quran_index))

    global_findings: list[dict[str, Any]] = list(validation_findings)
    if missing_core:
        global_findings.append({
            "code": "MISSING_CORE_VERSES",
            "count": len(missing_core),
            "verse_keys": missing_core,
        })
    if duplicate_core:
        global_findings.append({
            "code": "DUPLICATE_CORE_VERSES",
            "count": len(duplicate_core),
            "verse_keys": duplicate_core,
        })
    if invalid_core:
        global_findings.append({
            "code": "INVALID_CORE_VERSES",
            "count": len(invalid_core),
            "verse_keys": invalid_core,
        })

    # Finalize statuses only after global validation succeeds.
    if not global_findings:
        for dst in sorted(resolved_dir.glob("*__attempt-1.json")):
            data = load_json(dst)
            if data["resolution"]["changed_verses_in_packet"]:
                data["collection_status"] = "MANUALLY_ADJUDICATED_AND_VALIDATED"
            else:
                data["collection_status"] = "STRUCTURALLY_ACCEPTED"
            save_json(dst, data)

    report = {
        "run_name": args.run_name,
        "status": "PASS" if not global_findings else "FAIL",
        "quran_source_sha256": actual_sha,
        "source_quran_modified": False,
        "original_attempts_modified": False,
        "attempt_files": len(attempt_files),
        "numbered_quran_verses_expected": len(quran_index),
        "numbered_quran_verses_seen": len(seen_verses),
        "adjudications_expected": len(adjudications),
        "adjudications_applied": len(applied),
        "applied": applied,
        "validation_findings": global_findings,
    }

    save_json(report_dir / "phase1_resolution_report.json", report)

    txt = [
        "NAMES OF ALLAH — PHASE 1 RESOLUTION",
        "=====================================",
        "",
        f"Run: {args.run_name}",
        f"Status: {report['status']}",
        f"Quran SHA-256: {actual_sha}",
        f"Original attempts modified: NO",
        f"Quran source modified: NO",
        f"Attempt files: {len(attempt_files)}",
        f"Core verses expected: {len(quran_index)}",
        f"Core verses seen: {len(seen_verses)}",
        f"Adjudications applied: {len(applied)}",
        f"Validation findings: {len(global_findings)}",
        "",
        f"Resolved output: {resolved_dir.relative_to(PROJECT_ROOT)}",
        f"Report: {(report_dir / 'phase1_resolution_report.json').relative_to(PROJECT_ROOT)}",
    ]
    (report_dir / "phase1_resolution_report.txt").write_text(
        "\n".join(txt) + "\n",
        encoding="utf-8",
    )

    print("\n".join(txt))

    if global_findings:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
