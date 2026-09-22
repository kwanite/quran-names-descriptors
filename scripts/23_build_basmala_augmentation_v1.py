#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

EXPECTED_QURAN_SHA = "10b63cb29e329de93f80ff60eb332e52b3a72be8f68f6eb6272a03d4cb16084c"
EXPECTED_SURAHS = 114
EXPECTED_NUMBERED_AYAHS = 6236
EXPECTED_AYAH0 = 112
EXPECTED_MATCHES_PER_BASMALA = 3
EXPECTED_BASMALA_DESCRIPTOR_OCCURRENCES = 336

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def has_letter(s):
    return any(unicodedata.category(ch).startswith("L") for ch in s)

def tokens(text):
    out = []
    for m in re.finditer(r"\S+", text):
        if has_letter(m.group(0)):
            out.append((m.start(), m.end(), m.group(0)))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    repo = a.repo.resolve()

    quran_path = repo / "quran-simple-plain.json"
    corpus = repo / "runs/phase1_full_v3_2_1/semantic_exclusions_v2"
    out = repo / "runs/phase1_full_v3_2_1/finalization_v1/basmala_occurrences.json"
    if out.exists() and not a.overwrite:
        raise SystemExit(f"Refusing to overwrite existing output: {out}")

    if sha256(quran_path) != EXPECTED_QURAN_SHA:
        raise SystemExit("Quran SHA-256 mismatch. Refusing to augment basmalas.")

    q = load(quran_path)
    surahs = q.get("surahs")
    if not isinstance(surahs, list) or len(surahs) != EXPECTED_SURAHS:
        raise SystemExit("Unexpected Quran surah structure.")

    numbered = 0
    ayah0 = []
    for s in surahs:
        num = s.get("number")
        for arow in s.get("ayahs") or []:
            an = arow.get("number")
            if an == 0:
                ayah0.append({
                    "surah": num,
                    "ayah": 0,
                    "source_key": f"{num}:0",
                    "text": arow.get("text"),
                })
            elif isinstance(an, int) and an > 0:
                numbered += 1

    if numbered != EXPECTED_NUMBERED_AYAHS:
        raise SystemExit(f"Expected {EXPECTED_NUMBERED_AYAHS} numbered ayahs, got {numbered}")
    if len(ayah0) != EXPECTED_AYAH0:
        raise SystemExit(f"Expected {EXPECTED_AYAH0} ayah:0 records, got {len(ayah0)}")

    sm = load(corpus / "surface_to_lexeme_map_reviewed.json")
    surface_map = {}
    for m in sm["mappings"]:
        s = m["surface_arabic"]
        ident = m["lexical_identity_arabic"]
        if s in surface_map and surface_map[s] != ident:
            raise SystemExit(f"Surface maps to multiple identities: {s}")
        surface_map[s] = ident

    records = []
    identity_counts = Counter()

    for b in ayah0:
        matched = []
        for start, end, token in tokens(b["text"]):
            ident = surface_map.get(token)
            if ident is None:
                continue
            matched.append((start, end, token, ident))

        if len(matched) != EXPECTED_MATCHES_PER_BASMALA:
            raise SystemExit(
                f"{b['source_key']}: expected {EXPECTED_MATCHES_PER_BASMALA} descriptor tokens "
                f"from finalized surface map, found {len(matched)}: {matched}"
            )

        for i, (start, end, surface, ident) in enumerate(matched, 1):
            oid = f"basmala:{b['surah']}:0:d{i:02d}"
            records.append({
                "occurrence_id": oid,
                "record_type": "opening_basmala_unnumbered",
                "source_key": b["source_key"],
                "surah": b["surah"],
                "ayah": 0,
                "verse_key": None,
                "verse_text": b["text"],
                "surface_arabic": surface,
                "start_offset": start,
                "end_offset": end,
                "lexical_identity_arabic": ident,
                "qac_root_link_status": "NOT_AVAILABLE_AYAH0_NO_QAC",
            })
            identity_counts[ident] += 1

    if len(records) != EXPECTED_BASMALA_DESCRIPTOR_OCCURRENCES:
        raise SystemExit(
            f"Expected {EXPECTED_BASMALA_DESCRIPTOR_OCCURRENCES} basmala descriptor occurrences, got {len(records)}"
        )

    if sorted(identity_counts.values()) != [112, 112, 112]:
        raise SystemExit(f"Expected exactly three identities with 112 basmala occurrences each: {identity_counts}")

    output = {
        "version": "basmala-augmentation-v1",
        "source_semantic_version": "semantic-exclusions-v2",
        "quran_source_sha256": EXPECTED_QURAN_SHA,
        "policy": {
            "ayah0_is_not_canonical_numbered_verse": True,
            "new_lexical_identities_created": False,
            "matching_rule": "Exact full-token lookup against finalized exact-surface -> lexical-identity map.",
            "qac_links_fabricated": False,
        },
        "summary": {
            "numbered_ayah_count": numbered,
            "ayah0_basmala_count": len(ayah0),
            "basmala_descriptor_occurrence_count": len(records),
            "identity_counts": dict(sorted(identity_counts.items())),
        },
        "occurrences": records,
    }
    dump(out, output)
    print("BASMALA AUGMENTATION: PASS")
    print(f"Ayah:0 basmalas: {len(ayah0)}")
    print(f"Descriptor occurrences added: {len(records)}")
    print(f"Identities: {dict(identity_counts)}")
    print(f"Output: {out}")

if __name__ == "__main__":
    main()
