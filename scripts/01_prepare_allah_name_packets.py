#!/usr/bin/env python3
"""
01_prepare_allah_name_packets.py

Deterministically prepare Quran-only LLM analysis packets for the
"Names of Allah" extraction project.

Repository layout assumed by default:

names_of_Allah/
├── AGENT.md
├── quran-simple-plain.json
├── scripts/
│   └── 01_prepare_allah_name_packets.py
└── runs/
    └── preprocessing_v1/

Design invariants:
- Canonical LLM-processing universe is ayah > 0 only.
- Exactly 114 surahs and 6,236 canonical verses are expected.
- The 112 ayah:0 opening basmalas are preserved verbatim in run metadata.
- ayah:0 records are NEVER sent to the LLM as CORE or context.
- ayah:0 records are NOT discarded: they are explicitly deferred to a later
  deterministic basmala reconciliation step, where their known Quran text can
  contribute separate basmala occurrence counts.
- A packet NEVER contains verses from more than one surah.
- Short surahs are NEVER combined with another surah.
- Long surahs are divided into bounded CORE chunks.
- Context is same-surah only and explicitly separated into:
    context_before
    core_verses
    context_after
- Every canonical verse appears as CORE exactly once.
- Full same-surah canonical context is supplied around each CORE chunk.
- Quran text is copied verbatim; this script does not normalize or modify it.
- The script fails closed on structural/count/coverage anomalies.
- Existing non-empty run directories are never overwritten.

No OpenAI/API call is made by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

EXPECTED_SURAH_COUNT = 114
EXPECTED_CANONICAL_VERSE_COUNT = 6236
EXPECTED_AYAH0_BASMALA_COUNT = 112

TASK_ID = "names-of-allah-quran-only-v1"
SCRIPT_VERSION = "1.1"
PACKET_SCHEMA_VERSION = "1.0"
RUN_NAME_DEFAULT = "preprocessing_v1"


class ValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalVerse:
    surah: int
    ayah: int
    text: str

    @property
    def verse_key(self) -> str:
        return f"{self.surah}:{self.ayah}"

    def as_packet_record(self, role: str) -> dict[str, Any]:
        return {
            "verse_key": self.verse_key,
            "surah": self.surah,
            "ayah": self.ayah,
            "role": role,
            "text": self.text,
        }


@dataclass(frozen=True)
class SurahData:
    number: int
    name: str
    loc: str | None
    canonical_verses: tuple[CanonicalVerse, ...]
    opening_basmala_records: tuple[dict[str, Any], ...]


def die(message: str) -> NoReturn:
    raise ValidationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, value: Any, *, pretty: bool = True) -> None:
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    atomic_write_text(path, text)


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        die(f"Input Quran file does not exist: {path}")
    except OSError as exc:
        die(f"Could not read input Quran file {path}: {exc}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"Input Quran file is not valid JSON: {exc}")

    if not isinstance(data, dict):
        die("Top-level Quran JSON must be an object.")
    return data


def validate_and_parse_quran(
    data: dict[str, Any],
) -> tuple[list[SurahData], list[dict[str, Any]]]:
    raw_surahs = data.get("surahs")
    if not isinstance(raw_surahs, list):
        die("Top-level key 'surahs' must be a list.")

    if len(raw_surahs) != EXPECTED_SURAH_COUNT:
        die(
            f"Expected {EXPECTED_SURAH_COUNT} surahs, found {len(raw_surahs)}. "
            "Refusing to build packets from an unexpected corpus."
        )

    seen_surahs: set[int] = set()
    seen_canonical_keys: set[str] = set()
    parsed_surahs: list[SurahData] = []
    all_ayah0: list[dict[str, Any]] = []

    for raw_surah in raw_surahs:
        if not isinstance(raw_surah, dict):
            die("Every surah entry must be an object.")

        number = raw_surah.get("number")
        name = raw_surah.get("name")
        loc = raw_surah.get("loc")
        ayahs = raw_surah.get("ayahs")

        if not isinstance(number, int) or not (1 <= number <= EXPECTED_SURAH_COUNT):
            die(f"Invalid surah number: {number!r}")
        if number in seen_surahs:
            die(f"Duplicate surah number: {number}")
        seen_surahs.add(number)

        if not isinstance(name, str) or not name.strip():
            die(f"Surah {number}: missing/non-string Arabic name.")
        if loc is not None and not isinstance(loc, str):
            die(f"Surah {number}: 'loc' must be a string or null.")
        if not isinstance(ayahs, list):
            die(f"Surah {number}: 'ayahs' must be a list.")

        canonical: list[CanonicalVerse] = []
        ayah0_records: list[dict[str, Any]] = []
        seen_ayah_numbers: set[int] = set()

        for raw_ayah in ayahs:
            if not isinstance(raw_ayah, dict):
                die(f"Surah {number}: every ayah must be an object.")

            ayah_num = raw_ayah.get("number")
            text = raw_ayah.get("text")

            if not isinstance(ayah_num, int) or ayah_num < 0:
                die(f"Surah {number}: invalid ayah number {ayah_num!r}.")
            if ayah_num in seen_ayah_numbers:
                die(f"Surah {number}: duplicate ayah number {ayah_num}.")
            seen_ayah_numbers.add(ayah_num)

            if not isinstance(text, str) or text == "":
                die(f"Surah {number}:{ayah_num}: Quran text must be non-empty.")

            if ayah_num == 0:
                record = {
                    "surah": number,
                    "ayah": 0,
                    "source_key": f"{number}:0",
                    "record_type": "opening_basmala_unnumbered",
                    "text": text,
                    "llm_processing": "EXCLUDED",
                    "later_treatment": (
                        "DEFERRED_TO_DETERMINISTIC_BASMALA_RECONCILIATION"
                    ),
                }
                ayah0_records.append(record)
                all_ayah0.append(record)
                continue

            verse = CanonicalVerse(number, ayah_num, text)
            if verse.verse_key in seen_canonical_keys:
                die(f"Duplicate canonical verse key: {verse.verse_key}")
            seen_canonical_keys.add(verse.verse_key)
            canonical.append(verse)

        if not canonical:
            die(f"Surah {number}: no canonical ayahs found.")

        canonical.sort(key=lambda v: v.ayah)
        expected_numbers = list(range(1, len(canonical) + 1))
        actual_numbers = [v.ayah for v in canonical]
        if actual_numbers != expected_numbers:
            die(f"Surah {number}: canonical ayahs are not contiguous 1..N.")

        expected_ayah0 = 0 if number in (1, 9) else 1
        if len(ayah0_records) != expected_ayah0:
            die(
                f"Surah {number}: expected {expected_ayah0} ayah:0 record(s), "
                f"found {len(ayah0_records)}."
            )

        parsed_surahs.append(
            SurahData(
                number=number,
                name=name,
                loc=loc,
                canonical_verses=tuple(canonical),
                opening_basmala_records=tuple(ayah0_records),
            )
        )

    parsed_surahs.sort(key=lambda s: s.number)

    if [s.number for s in parsed_surahs] != list(range(1, 115)):
        die("Surah identity set is not exactly 1..114.")

    canonical_count = sum(len(s.canonical_verses) for s in parsed_surahs)
    if canonical_count != EXPECTED_CANONICAL_VERSE_COUNT:
        die(
            f"Expected {EXPECTED_CANONICAL_VERSE_COUNT} canonical verses, "
            f"found {canonical_count}."
        )

    if len(all_ayah0) != EXPECTED_AYAH0_BASMALA_COUNT:
        die(
            f"Expected {EXPECTED_AYAH0_BASMALA_COUNT} ayah:0 basmalas, "
            f"found {len(all_ayah0)}."
        )

    if not any(v.verse_key == "1:1" for v in parsed_surahs[0].canonical_verses):
        die("Canonical verse 1:1 is missing.")

    return parsed_surahs, all_ayah0


def make_packet(
    *,
    source_sha256: str,
    surah: SurahData,
    global_packet_number: int,
    chunk_number: int,
    total_chunks_for_surah: int,
    core_start_index: int,
    core_end_index_exclusive: int,
    core_size_limit: int,
) -> dict[str, Any]:
    verses = list(surah.canonical_verses)
    core = verses[core_start_index:core_end_index_exclusive]
    before = verses[:core_start_index]
    after = verses[core_end_index_exclusive:]

    if not core:
        die(f"Internal error: empty CORE chunk for surah {surah.number}.")

    packet_id = (
        f"allah-names-v1-s{surah.number:03d}"
        f"-c{chunk_number:02d}"
        f"-a{core[0].ayah:03d}-{core[-1].ayah:03d}"
    )

    return {
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "packet_id": packet_id,
        "global_packet_number": global_packet_number,
        "source": {
            "source_sha256": source_sha256,
            "canonical_verse_universe": EXPECTED_CANONICAL_VERSE_COUNT,
            "ayah0_opening_basmalas_excluded_from_llm": True,
            "ayah0_opening_basmalas_deferred_to_deterministic_reconciliation": True,
        },
        "surah": {
            "number": surah.number,
            "name": surah.name,
            "loc": surah.loc,
            "canonical_ayah_count": len(verses),
        },
        "chunk": {
            "chunk_number_within_surah": chunk_number,
            "total_chunks_for_surah": total_chunks_for_surah,
            "core_size_limit": core_size_limit,
            "core_first_ayah": core[0].ayah,
            "core_last_ayah": core[-1].ayah,
            "core_verse_count": len(core),
        },
        "processing_contract": {
            "surah_boundary_is_absolute": True,
            "contains_exactly_one_surah": True,
            "process_only_key": "core_verses",
            "context_only_keys": ["context_before", "context_after"],
            "context_is_same_surah_only": True,
            "context_policy": (
                "FULL_SAME_SURAH_CONTEXT: every canonical verse in this surah "
                "outside the CORE chunk is supplied only as context."
            ),
            "must_return_exactly_one_verse_result_per_core_verse": True,
            "must_not_emit_results_for_context_only_verses": True,
            "quran_text_must_be_treated_as_verbatim": True,
        },
        "context_before": [
            v.as_packet_record("CONTEXT_ONLY_BEFORE") for v in before
        ],
        "core_verses": [
            v.as_packet_record("CORE_PROCESS") for v in core
        ],
        "context_after": [
            v.as_packet_record("CONTEXT_ONLY_AFTER") for v in after
        ],
    }


def packet_filename(packet: dict[str, Any]) -> str:
    return f"{packet['packet_id']}.json"


def audit_packets(
    *,
    packets: list[dict[str, Any]],
    surahs: list[SurahData],
    core_size: int,
) -> dict[str, Any]:
    canonical_by_surah = {
        s.number: {v.verse_key for v in s.canonical_verses} for s in surahs
    }
    expected_core_keys = {
        v.verse_key for s in surahs for v in s.canonical_verses
    }

    core_counter: Counter[str] = Counter()
    foreign_surah_violations: list[str] = []
    overlap_violations: list[str] = []
    context_coverage_violations: list[str] = []
    core_size_violations: list[str] = []
    role_violations: list[str] = []

    max_packet_text_chars = 0
    max_packet_id = None
    total_repeated_text_chars = 0

    for packet in packets:
        packet_id = packet["packet_id"]
        s_num = packet["surah"]["number"]

        before = packet["context_before"]
        core = packet["core_verses"]
        after = packet["context_after"]

        if len(core) > core_size or len(core) == 0:
            core_size_violations.append(packet_id)

        all_records = before + core + after

        for record in all_records:
            if record["surah"] != s_num:
                foreign_surah_violations.append(
                    f"{packet_id}: {record['verse_key']} belongs to "
                    f"surah {record['surah']}"
                )

        before_keys = {r["verse_key"] for r in before}
        core_keys = {r["verse_key"] for r in core}
        after_keys = {r["verse_key"] for r in after}

        if before_keys & core_keys or core_keys & after_keys or before_keys & after_keys:
            overlap_violations.append(packet_id)

        if before_keys | core_keys | after_keys != canonical_by_surah[s_num]:
            context_coverage_violations.append(packet_id)

        for r in before:
            if r["role"] != "CONTEXT_ONLY_BEFORE":
                role_violations.append(f"{packet_id}:{r['verse_key']}")
        for r in core:
            if r["role"] != "CORE_PROCESS":
                role_violations.append(f"{packet_id}:{r['verse_key']}")
            core_counter[r["verse_key"]] += 1
        for r in after:
            if r["role"] != "CONTEXT_ONLY_AFTER":
                role_violations.append(f"{packet_id}:{r['verse_key']}")

        packet_text_chars = sum(len(r["text"]) for r in all_records)
        total_repeated_text_chars += packet_text_chars
        if packet_text_chars > max_packet_text_chars:
            max_packet_text_chars = packet_text_chars
            max_packet_id = packet_id

    actual_core_keys = set(core_counter)
    missing = sorted(expected_core_keys - actual_core_keys)
    unexpected = sorted(actual_core_keys - expected_core_keys)
    non_unique = sorted(k for k, count in core_counter.items() if count != 1)

    errors = {
        "missing_core_verse_keys": missing,
        "unexpected_core_verse_keys": unexpected,
        "non_unique_core_verse_keys": non_unique,
        "foreign_surah_violations": foreign_surah_violations,
        "section_overlap_violations": overlap_violations,
        "full_same_surah_context_coverage_violations": context_coverage_violations,
        "core_size_violations": core_size_violations,
        "role_violations": role_violations,
    }
    error_count = sum(len(v) for v in errors.values())

    return {
        "status": "PASS" if error_count == 0 else "FAIL",
        "packet_count": len(packets),
        "expected_canonical_core_verses": len(expected_core_keys),
        "actual_unique_core_verses": len(actual_core_keys),
        "total_core_assignments": sum(core_counter.values()),
        "core_assignment_exactly_once": error_count == 0,
        "cross_surah_mixing_detected": bool(foreign_surah_violations),
        "max_packet_quran_text_chars": max_packet_text_chars,
        "max_packet_quran_text_chars_packet_id": max_packet_id,
        "total_quran_text_chars_sent_across_all_packets_before_prompt_overhead": (
            total_repeated_text_chars
        ),
        "errors": errors,
    }


def ensure_fresh_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        try:
            has_contents = any(output_dir.iterdir())
        except OSError as exc:
            die(f"Could not inspect output directory {output_dir}: {exc}")
        if has_contents:
            die(
                f"Run directory already exists and is not empty: {output_dir}\n"
                "Refusing to overwrite prior evidence. Use a new --run-name."
            )
    output_dir.mkdir(parents=True, exist_ok=True)


def report_text(
    *,
    repo_root: Path,
    input_path: Path,
    output_dir: Path,
    source_sha256: str,
    core_size: int,
    surahs: list[SurahData],
    all_ayah0: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    audit: dict[str, Any],
) -> str:
    lines = [
        "NAMES OF ALLAH — PREPROCESSING REPORT",
        "=" * 44,
        "",
        f"Status: {audit['status']}",
        f"Script version: {SCRIPT_VERSION}",
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "REPOSITORY",
        f"Repo root: {repo_root}",
        f"Input: {input_path}",
        f"Run directory: {output_dir}",
        "",
        "SOURCE",
        f"SHA-256: {source_sha256}",
        f"Surahs: {len(surahs)}",
        f"Canonical numbered verses: {sum(len(s.canonical_verses) for s in surahs)}",
        f"Unnumbered ayah:0 basmalas preserved: {len(all_ayah0)}",
        "ayah:0 LLM treatment: EXCLUDED",
        "ayah:0 later treatment: DETERMINISTIC BASMALA RECONCILIATION",
        "",
        "PACKET POLICY",
        f"Maximum CORE verses per packet: {core_size}",
        "Surahs per packet: exactly 1",
        "Short surahs combined: NEVER",
        "Context: full canonical context from the SAME surah only",
        "Explicit sections: context_before / core_verses / context_after",
        "LLM may process: core_verses ONLY",
        "",
        "OUTPUT",
        f"Packets generated: {len(packets)}",
        f"Unique CORE verses assigned: {audit['actual_unique_core_verses']}",
        f"CORE assignments exactly once: {audit['core_assignment_exactly_once']}",
        f"Cross-surah mixing detected: {audit['cross_surah_mixing_detected']}",
        f"Max Quran text chars in one packet: {audit['max_packet_quran_text_chars']} "
        f"({audit['max_packet_quran_text_chars_packet_id']})",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_repo_root = script_path.parent.parent

    parser = argparse.ArgumentParser(
        description=(
            "Create deterministic same-surah Quran packets for the Names-of-Allah "
            "LLM Batch extraction. Makes no API calls."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root,
        help=(
            "Repository root. Default is the parent of this script's scripts/ "
            "directory."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Quran JSON path. Default: <repo-root>/quran-simple-plain.json"
        ),
    )
    parser.add_argument(
        "--run-name",
        default=RUN_NAME_DEFAULT,
        help="Fresh run directory name under <repo-root>/runs/",
    )
    parser.add_argument(
        "--core-size",
        type=int,
        default=50,
        help="Maximum number of CORE verses per request (default: 50).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.core_size < 1 or args.core_size > 100:
        raise ValidationError("--core-size must be between 1 and 100.")

    repo_root = args.repo_root.expanduser().resolve()
    input_path = (
        args.input.expanduser().resolve()
        if args.input is not None
        else repo_root / "quran-simple-plain.json"
    )
    output_dir = repo_root / "runs" / args.run_name

    data = load_json(input_path)
    source_sha256 = sha256_file(input_path)
    surahs, all_ayah0 = validate_and_parse_quran(data)

    packets: list[dict[str, Any]] = []
    packet_no = 0

    for surah in surahs:
        verse_count = len(surah.canonical_verses)
        total_chunks = math.ceil(verse_count / args.core_size)

        for chunk_idx, start in enumerate(
            range(0, verse_count, args.core_size), start=1
        ):
            end = min(start + args.core_size, verse_count)
            packet_no += 1
            packets.append(
                make_packet(
                    source_sha256=source_sha256,
                    surah=surah,
                    global_packet_number=packet_no,
                    chunk_number=chunk_idx,
                    total_chunks_for_surah=total_chunks,
                    core_start_index=start,
                    core_end_index_exclusive=end,
                    core_size_limit=args.core_size,
                )
            )

    audit = audit_packets(
        packets=packets,
        surahs=surahs,
        core_size=args.core_size,
    )
    if audit["status"] != "PASS":
        raise ValidationError(
            "Internal packet audit failed before output was written:\n"
            + json.dumps(audit["errors"], ensure_ascii=False, indent=2)
        )

    ensure_fresh_output_dir(output_dir)
    packets_dir = output_dir / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)

    source_manifest = {
        "manifest_schema_version": "1.1",
        "task_id": TASK_ID,
        "script_version": SCRIPT_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "input_path": str(input_path),
        "source_sha256": source_sha256,
        "source_metadata": data.get("metadata", {}),
        "canonical_policy": {
            "canonical_llm_processing_rule": "ayah > 0",
            "canonical_verse_count": EXPECTED_CANONICAL_VERSE_COUNT,
            "surah_count": EXPECTED_SURAH_COUNT,
            "ayah0_opening_basmala_count": EXPECTED_AYAH0_BASMALA_COUNT,
            "ayah0_llm_treatment": "EXCLUDED",
            "ayah0_reconciliation_treatment": (
                "DEFERRED_TO_DETERMINISTIC_BASMALA_RECONCILIATION"
            ),
            "final_counting_intent": (
                "Keep canonical numbered-verse occurrences separate from "
                "unnumbered opening-basmala occurrences, then expose a total "
                "that may include both after deterministic reconciliation."
            ),
            "surah_1_1_treatment": (
                "1:1 is canonical and is processed normally by the LLM."
            ),
        },
        "packet_policy": {
            "core_size": args.core_size,
            "surahs_per_packet": 1,
            "combine_short_surahs": False,
            "allow_cross_surah_context": False,
            "context_mode": "full_same_surah",
            "explicit_sections": [
                "context_before",
                "core_verses",
                "context_after",
            ],
        },
        "excluded_ayah0_records": all_ayah0,
    }
    atomic_write_json(output_dir / "source_manifest.json", source_manifest)

    for packet in packets:
        atomic_write_json(packets_dir / packet_filename(packet), packet)

    jsonl_text = "".join(
        json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n"
        for packet in packets
    )
    atomic_write_text(output_dir / "packets.jsonl", jsonl_text)

    packet_manifest = {
        "manifest_schema_version": "1.0",
        "task_id": TASK_ID,
        "source_sha256": source_sha256,
        "core_size": args.core_size,
        "packet_count": len(packets),
        "packets": [
            {
                "packet_id": p["packet_id"],
                "global_packet_number": p["global_packet_number"],
                "filename": f"packets/{packet_filename(p)}",
                "surah": p["surah"]["number"],
                "surah_name": p["surah"]["name"],
                "chunk_number_within_surah": p["chunk"]["chunk_number_within_surah"],
                "total_chunks_for_surah": p["chunk"]["total_chunks_for_surah"],
                "core_first_ayah": p["chunk"]["core_first_ayah"],
                "core_last_ayah": p["chunk"]["core_last_ayah"],
                "core_verse_count": p["chunk"]["core_verse_count"],
                "context_before_count": len(p["context_before"]),
                "context_after_count": len(p["context_after"]),
                "core_verse_keys": [r["verse_key"] for r in p["core_verses"]],
            }
            for p in packets
        ],
    }
    atomic_write_json(output_dir / "packet_manifest.json", packet_manifest)

    preprocessing_report = {
        "report_schema_version": "1.1",
        "task_id": TASK_ID,
        "script_version": SCRIPT_VERSION,
        "status": audit["status"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source_sha256,
        "core_size": args.core_size,
        "surah_count": len(surahs),
        "canonical_verse_count": sum(len(s.canonical_verses) for s in surahs),
        "ayah0_opening_basmala_count": len(all_ayah0),
        "packet_count": len(packets),
        "audit": audit,
        "per_surah": [
            {
                "surah": s.number,
                "name": s.name,
                "canonical_verse_count": len(s.canonical_verses),
                "packet_count": math.ceil(
                    len(s.canonical_verses) / args.core_size
                ),
            }
            for s in surahs
        ],
    }
    atomic_write_json(
        output_dir / "preprocessing_report.json", preprocessing_report
    )

    txt = report_text(
        repo_root=repo_root,
        input_path=input_path,
        output_dir=output_dir,
        source_sha256=source_sha256,
        core_size=args.core_size,
        surahs=surahs,
        all_ayah0=all_ayah0,
        packets=packets,
        audit=audit,
    )
    atomic_write_text(output_dir / "preprocessing_report.txt", txt)

    run_readme = f"""# Preprocessing run: {args.run_name}

Generated by `scripts/01_prepare_allah_name_packets.py` version {SCRIPT_VERSION}.

## Status

`{audit['status']}`

## Source

- Quran file: `quran-simple-plain.json`
- SHA-256: `{source_sha256}`
- Canonical numbered verses: {EXPECTED_CANONICAL_VERSE_COUNT}
- Preserved unnumbered opening basmalas: {len(all_ayah0)}

## Packet policy

- Maximum CORE verses: {args.core_size}
- Exactly one surah per packet.
- Short surahs are never combined.
- Context is restricted to the same surah.
- Full same-surah canonical context is supplied around every CORE chunk.
- The model must process only `core_verses`.
- `context_before` and `context_after` are context-only.
- Every canonical numbered verse is CORE exactly once.

## Basmala policy

The 112 unnumbered `ayah:0` opening basmalas are excluded from LLM processing
but preserved verbatim in `source_manifest.json`. They are intentionally
deferred to deterministic reconciliation. Final data should keep canonical
numbered-verse occurrences separate from unnumbered opening-basmala
occurrences, while allowing a derived total count that includes both.

## Files

- `source_manifest.json`
- `packet_manifest.json`
- `packets.jsonl`
- `preprocessing_report.json`
- `preprocessing_report.txt`
- `packets/`
"""
    atomic_write_text(output_dir / "README.md", run_readme)

    print(txt, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
