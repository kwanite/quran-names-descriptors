#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QURAN_FILE = PROJECT_ROOT / "quran-simple-plain.json"


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


def resolve_positions(source: str, values: list[str], field_name: str, verse_key: str):
    used = Counter()
    resolved = []
    previous_start = -1

    for ordinal, value in enumerate(values, 1):
        positions = literal_positions(source, value)
        if not positions:
            raise RuntimeError(
                f"{verse_key} {field_name}[{ordinal}] is not an exact substring: {value}"
            )

        n = used[value]
        if n >= len(positions):
            raise RuntimeError(
                f"{verse_key} {field_name}[{ordinal}] exceeds source occurrences: {value}"
            )

        start = positions[n]
        end = start + len(value)
        used[value] += 1

        if start < previous_start:
            raise RuntimeError(
                f"{verse_key} {field_name} is not in source order"
            )
        previous_start = start

        resolved.append({
            "ordinal": ordinal,
            "surface_arabic": value,
            "start_offset": start,
            "end_offset": end,
            "surface_occurrence_index_in_verse": used[value],
        })

    return resolved


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build the deterministic Phase-1 occurrence ledger and exact-surface inventory."
    )
    ap.add_argument("--run-name", required=True)
    args = ap.parse_args()

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    resolved_dir = run_dir / "resolved_attempts"
    resolution_report = run_dir / "resolution" / "phase1_resolution_report.json"

    if not resolved_dir.is_dir():
        raise SystemExit(f"Missing resolved attempts: {resolved_dir}")
    if not resolution_report.is_file():
        raise SystemExit(f"Missing Phase-1 resolution report: {resolution_report}")
    if not QURAN_FILE.is_file():
        raise SystemExit(f"Missing Quran source: {QURAN_FILE}")

    resolution = load_json(resolution_report)
    if resolution.get("status") != "PASS":
        raise SystemExit("Phase-1 resolution report is not PASS")

    quran_sha = sha256_file(QURAN_FILE)
    if quran_sha != resolution.get("quran_source_sha256"):
        raise SystemExit(
            "Quran SHA-256 does not match the frozen Phase-1 resolution report"
        )

    quran = load_json(QURAN_FILE)
    quran_index = build_quran_index(quran)

    if len(quran_index) != 6236:
        raise SystemExit(f"Expected 6236 numbered verses, found {len(quran_index)}")

    attempt_files = sorted(resolved_dir.glob("*__attempt-1.json"))
    if len(attempt_files) != 190:
        raise SystemExit(f"Expected 190 resolved attempt files, found {len(attempt_files)}")

    verse_seen = Counter()
    occurrences = []
    manual_review_occurrences = []
    surface_counts = Counter()
    surface_locations = defaultdict(list)
    packet_status_counts = Counter()

    for path in attempt_files:
        attempt = load_json(path)
        packet_id = attempt.get("packet_id")
        packet_status_counts[attempt.get("collection_status", "UNKNOWN")] += 1

        parsed = attempt.get("parsed_output")
        if not isinstance(parsed, dict):
            raise SystemExit(f"Missing parsed_output in {path.name}")

        verse_results = parsed.get("verse_results")
        if not isinstance(verse_results, list):
            raise SystemExit(f"Missing verse_results in {path.name}")

        deterministic_repairs = attempt.get("deterministic_repairs") or []
        repaired_verse_keys = {
            r.get("verse_key")
            for r in deterministic_repairs
            if isinstance(r, dict)
        }
        adjudicated_verse_keys = set()
        for applied in resolution.get("applied", []):
            if applied.get("packet_id") == packet_id:
                adjudicated_verse_keys.add(applied.get("verse_key"))

        for vr in verse_results:
            verse_key = vr.get("verse_key")
            if verse_key not in quran_index:
                raise SystemExit(f"Invalid verse key in resolved output: {verse_key}")

            verse_seen[verse_key] += 1
            source = quran_index[verse_key]

            descriptors = vr.get("descriptors")
            manual = vr.get("manual_review")
            if not isinstance(descriptors, list) or not isinstance(manual, list):
                raise SystemExit(f"Invalid descriptor/manual_review lists at {verse_key}")

            descriptor_positions = resolve_positions(
                source, descriptors, "descriptors", verse_key
            )
            manual_positions = resolve_positions(
                source, manual, "manual_review", verse_key
            )

            for item in descriptor_positions:
                occurrence_id = f"{verse_key}:d{item['ordinal']:02d}"
                record = {
                    "occurrence_id": occurrence_id,
                    "packet_id": packet_id,
                    "verse_key": verse_key,
                    "verse_text": source,
                    "surface_arabic": item["surface_arabic"],
                    "descriptor_ordinal_in_verse": item["ordinal"],
                    "surface_occurrence_index_in_verse": item["surface_occurrence_index_in_verse"],
                    "start_offset": item["start_offset"],
                    "end_offset": item["end_offset"],
                    "manual_review": False,
                    "allah_deterministic_reconciliation_applied_to_verse": verse_key in repaired_verse_keys,
                    "manual_adjudication_applied_to_verse": verse_key in adjudicated_verse_keys,
                }
                occurrences.append(record)
                surface_counts[item["surface_arabic"]] += 1
                surface_locations[item["surface_arabic"]].append({
                    "occurrence_id": occurrence_id,
                    "verse_key": verse_key,
                    "start_offset": item["start_offset"],
                    "end_offset": item["end_offset"],
                })

            for item in manual_positions:
                occurrence_id = f"{verse_key}:m{item['ordinal']:02d}"
                manual_review_occurrences.append({
                    "occurrence_id": occurrence_id,
                    "packet_id": packet_id,
                    "verse_key": verse_key,
                    "verse_text": source,
                    "surface_arabic": item["surface_arabic"],
                    "manual_review_ordinal_in_verse": item["ordinal"],
                    "surface_occurrence_index_in_verse": item["surface_occurrence_index_in_verse"],
                    "start_offset": item["start_offset"],
                    "end_offset": item["end_offset"],
                    "manual_review": True,
                })

    missing = sorted(set(quran_index) - set(verse_seen))
    duplicate = sorted(k for k, n in verse_seen.items() if n != 1)
    extra = sorted(set(verse_seen) - set(quran_index))

    if missing or duplicate or extra:
        raise SystemExit(
            f"Global coverage failure: missing={len(missing)} duplicate={len(duplicate)} extra={len(extra)}"
        )

    inventory = []
    for surface, count in sorted(
        surface_counts.items(),
        key=lambda kv: (-kv[1], kv[0]),
    ):
        inventory.append({
            "surface_arabic": surface,
            "occurrence_count": count,
            "occurrences": surface_locations[surface],
        })

    out_dir = run_dir / "phase2_preparation"
    if out_dir.exists():
        raise SystemExit(
            f"Refusing to overwrite existing Phase-2 preparation output: {out_dir}"
        )
    out_dir.mkdir(parents=True)

    ledger_path = out_dir / "phase1_occurrence_ledger.json"
    inventory_path = out_dir / "exact_surface_inventory.json"
    manual_path = out_dir / "manual_review_occurrences.json"
    report_path = out_dir / "phase1_inventory_report.json"
    report_txt_path = out_dir / "phase1_inventory_report.txt"

    save_json(ledger_path, {
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "occurrence_count": len(occurrences),
        "occurrences": occurrences,
    })

    save_json(inventory_path, {
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "distinct_exact_surfaces": len(inventory),
        "descriptor_occurrences": len(occurrences),
        "inventory": inventory,
    })

    save_json(manual_path, {
        "run_name": args.run_name,
        "quran_source_sha256": quran_sha,
        "manual_review_count": len(manual_review_occurrences),
        "occurrences": manual_review_occurrences,
    })

    frequencies = Counter(surface_counts.values())
    top20 = [
        {"surface_arabic": surface, "occurrence_count": count}
        for surface, count in surface_counts.most_common(20)
    ]

    report = {
        "run_name": args.run_name,
        "status": "PASS",
        "quran_source_sha256": quran_sha,
        "resolved_attempt_files": len(attempt_files),
        "numbered_quran_verses": len(verse_seen),
        "descriptor_occurrences": len(occurrences),
        "distinct_exact_surfaces": len(inventory),
        "manual_review_occurrences": len(manual_review_occurrences),
        "surface_frequency_distribution": {
            str(freq): number_of_surfaces
            for freq, number_of_surfaces in sorted(frequencies.items())
        },
        "top_20_exact_surfaces": top20,
        "packet_status_counts": dict(packet_status_counts),
        "outputs": {
            "occurrence_ledger": str(ledger_path.relative_to(PROJECT_ROOT)),
            "exact_surface_inventory": str(inventory_path.relative_to(PROJECT_ROOT)),
            "manual_review_occurrences": str(manual_path.relative_to(PROJECT_ROOT)),
        },
    }
    save_json(report_path, report)

    txt = [
        "NAMES OF ALLAH — PHASE 2 PREPARATION INVENTORY",
        "================================================",
        "",
        f"Run: {args.run_name}",
        "Status: PASS",
        f"Quran SHA-256: {quran_sha}",
        f"Resolved attempt files: {len(attempt_files)}",
        f"Numbered Quran verses: {len(verse_seen)}",
        f"Descriptor occurrences: {len(occurrences)}",
        f"Distinct exact surfaces: {len(inventory)}",
        f"Manual-review occurrences: {len(manual_review_occurrences)}",
        "",
        "Top exact surfaces:",
    ]
    for row in top20:
        txt.append(f"{row['occurrence_count']:5d}  {row['surface_arabic']}")

    txt += [
        "",
        f"Occurrence ledger: {ledger_path.relative_to(PROJECT_ROOT)}",
        f"Exact-surface inventory: {inventory_path.relative_to(PROJECT_ROOT)}",
        f"Manual-review file: {manual_path.relative_to(PROJECT_ROOT)}",
        f"JSON report: {report_path.relative_to(PROJECT_ROOT)}",
    ]
    report_txt_path.write_text("\n".join(txt) + "\n", encoding="utf-8")
    print("\n".join(txt))


if __name__ == "__main__":
    main()
