#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def key(row):
    return (
        row["verse_key"],
        row["surface_arabic"],
        row["start_offset"],
        row["end_offset"],
    )


def format_key(k):
    verse_key, surface, start, end = k
    return f"{verse_key:>6}  [{start}:{end}]  {surface}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    args = ap.parse_args()

    run = PROJECT_ROOT / "runs" / args.run_name
    old_path = (
        run / "phase2_preparation" / "phase1_occurrence_ledger.json"
    )
    new_path = (
        run / "phase2_preparation_integrity_v1_2"
        / "phase1_occurrence_ledger.json"
    )

    if not old_path.is_file():
        raise SystemExit(f"Missing old ledger: {old_path}")
    if not new_path.is_file():
        raise SystemExit(
            "The v1.2 rebuild did not leave a corrected ledger at: "
            f"{new_path}"
        )

    old = load(old_path)["occurrences"]
    new = load(new_path)["occurrences"]

    old_counter = Counter(key(x) for x in old)
    new_counter = Counter(key(x) for x in new)

    removed = list((old_counter - new_counter).elements())
    added = list((new_counter - old_counter).elements())

    changed_verses = sorted(
        {x[0] for x in removed} | {x[0] for x in added},
        key=lambda s: tuple(map(int, s.split(":"))),
    )

    print("NAMES OF ALLAH — INTEGRITY COUNT DELTA")
    print("========================================")
    print()
    print(f"Old descriptor occurrences: {len(old)}")
    print(f"Corrected descriptor occurrences: {len(new)}")
    print(f"Net delta: {len(new) - len(old):+d}")
    print(f"Removed occurrence records: {len(removed)}")
    print(f"Added occurrence records: {len(added)}")
    print(f"Changed verses: {len(changed_verses)}")
    print()

    print("REMOVED")
    print("-------")
    for item in sorted(
        removed,
        key=lambda x: (
            tuple(map(int, x[0].split(":"))),
            x[2],
            x[1],
        ),
    ):
        print(format_key(item))

    print()
    print("ADDED")
    print("-----")
    for item in sorted(
        added,
        key=lambda x: (
            tuple(map(int, x[0].split(":"))),
            x[2],
            x[1],
        ),
    ):
        print(format_key(item))

    print()
    print("PER-VERSE OLD → CORRECTED")
    print("-------------------------")
    old_by = defaultdict(list)
    new_by = defaultdict(list)

    for row in old:
        old_by[row["verse_key"]].append(
            (row["start_offset"], row["surface_arabic"])
        )
    for row in new:
        new_by[row["verse_key"]].append(
            (row["start_offset"], row["surface_arabic"])
        )

    for verse_key in changed_verses:
        old_vals = [x[1] for x in sorted(old_by[verse_key])]
        new_vals = [x[1] for x in sorted(new_by[verse_key])]
        print(f"{verse_key}")
        print("  OLD:       " + " | ".join(old_vals))
        print("  CORRECTED: " + " | ".join(new_vals))

    print()
    print("No files were modified.")


if __name__ == "__main__":
    main()
