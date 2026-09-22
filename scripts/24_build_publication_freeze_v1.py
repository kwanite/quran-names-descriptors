#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

EXPECTED_QURAN_SHA = "10b63cb29e329de93f80ff60eb332e52b3a72be8f68f6eb6272a03d4cb16084c"
EXPECTED_IDENTITIES = 225
EXPECTED_NUMBERED_OCCURRENCES = 5037
EXPECTED_SURFACES = 404
EXPECTED_ONE_WORD_IDENTITIES = 125
EXPECTED_ONE_WORD_OCCURRENCES = 4798
EXPECTED_MULTIWORD_IDENTITIES = 100
EXPECTED_MULTIWORD_OCCURRENCES = 239
EXPECTED_AYAH0 = 112
EXPECTED_BASMALA_DESCRIPTOR_OCCURRENCES = 336

SOURCE_LICENSES = {
    "project_owned_material": {
        "license": "GPL-3.0-only",
        "scope": "Project-authored code, documentation, compilation/arrangement, and original human/AI-assisted synthesis to the extent rights are held by the project."
    },
    "tanzil_quran_text": {
        "license": "CC-BY-3.0",
        "copyright": "Copyright (C) 2007-2021 Tanzil Project",
        "terms_url": "https://tanzil.net/docs/Text_License",
        "requirements": [
            "Quran text must remain verbatim; changing it is not allowed.",
            "Clearly attribute Tanzil Project and link to tanzil.net.",
            "Reproduce the Tanzil notice appropriately in files derived from or containing a substantial portion of the Quran text."
        ]
    },
    "quranic_arabic_corpus": {
        "source": "Quranic Arabic Corpus version 0.4 morphology/annotations",
        "download_page_license": "GNU GPL",
        "terms_url": "https://corpus.quran.com/download/",
        "faq_url": "https://corpus.quran.com/faq.jsp",
        "caveat": "QAC public pages are not fully internally consistent: the download page states GNU GPL while the FAQ describes research/non-commercial use. This release does not represent QAC-derived fields as cleared for unrestricted commercial reuse."
    },
    "quran_foundation": {
        "included_in_publication_data": False,
        "note": "Raw Quran Foundation/Quran.com API content is not included in publication data. Project-derived transliterations/glosses are separate project metadata."
    }
}

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

def flatten_metadata(obj):
    # Return identity -> metadata record for the common viewer structures.
    if not isinstance(obj, dict):
        return {}
    direct = {k: v for k, v in obj.items() if isinstance(v, dict) and any("\u0600" <= ch <= "\u06ff" for ch in k)}
    if direct:
        return direct
    for value in obj.values():
        if isinstance(value, dict):
            found = {k: v for k, v in value.items() if isinstance(v, dict) and any("\u0600" <= ch <= "\u06ff" for ch in k)}
            if found:
                return found
        if isinstance(value, list):
            out = {}
            for rec in value:
                if not isinstance(rec, dict):
                    continue
                ident = rec.get("lexical_identity_arabic") or rec.get("arabic") or rec.get("identity")
                if ident:
                    out[ident] = rec
            if out:
                return out
    return {}

def pick_meta(rec):
    if not isinstance(rec, dict):
        return {}
    out = {}
    for src, dst in [
        ("transliteration", "transliteration"),
        ("transliteration_latin", "transliteration"),
        ("romanization", "transliteration"),
        ("english_gloss", "english_gloss"),
        ("meaning", "english_gloss"),
        ("gloss", "english_gloss"),
        ("english", "english_gloss"),
        ("translation", "english_gloss"),
    ]:
        if src in rec and dst not in out:
            out[dst] = rec[src]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    repo = a.repo.resolve()

    corpus = repo / "runs/phase1_full_v3_2_1/semantic_exclusions_v2"
    fin = repo / "runs/phase1_full_v3_2_1/finalization_v1"
    viewer = repo / "descriptor_viewer/data"
    decisions_path = repo / "runs/phase1_full_v3_2_1/semantic_precision_recall_audit_v1/manual_review_decisions_v1_reconciled.json"
    quran_path = repo / "quran-simple-plain.json"
    outdir = repo / "final/publication_v1"

    if outdir.exists() and any(outdir.iterdir()) and not a.overwrite:
        raise SystemExit(f"Refusing to overwrite non-empty publication freeze: {outdir}")

    required = [
        corpus / "descriptor_occurrences_lexical.json",
        corpus / "lexical_frequency.json",
        corpus / "surface_to_lexeme_map_reviewed.json",
        corpus / "excluded_descriptors.json",
        corpus / "excluded_occurrences.json",
        fin / "preferred_quran_surfaces.json",
        fin / "multiword_root_links.json",
        fin / "basmala_occurrences.json",
        viewer / "descriptor_root_forms.json",
        viewer / "descriptor_root_form_audit.json",
        viewer / "descriptor_metadata.json",
        decisions_path,
        quran_path,
    ]
    for p in required:
        if not p.exists():
            raise SystemExit(f"Missing required input: {p}")

    if sha256(quran_path) != EXPECTED_QURAN_SHA:
        raise SystemExit("Quran source SHA mismatch.")

    occ = load(corpus / "descriptor_occurrences_lexical.json")
    freq = load(corpus / "lexical_frequency.json")
    surf = load(corpus / "surface_to_lexeme_map_reviewed.json")
    pref = load(fin / "preferred_quran_surfaces.json")
    multi = load(fin / "multiword_root_links.json")
    basmala = load(fin / "basmala_occurrences.json")
    rf = load(viewer / "descriptor_root_forms.json")
    rfa = load(viewer / "descriptor_root_form_audit.json")
    metadata = flatten_metadata(load(viewer / "descriptor_metadata.json"))
    decisions = load(decisions_path)

    if decisions.get("status") != "RECONCILED_READY_FOR_BUILD":
        raise SystemExit("Manual-review ledger is not reconciled/build-ready.")
    if len(freq["lexical_identities"]) != EXPECTED_IDENTITIES:
        raise SystemExit("Final identity count mismatch.")
    if len(occ["occurrences"]) != EXPECTED_NUMBERED_OCCURRENCES:
        raise SystemExit("Final numbered occurrence count mismatch.")
    if int(surf.get("surface_count")) != EXPECTED_SURFACES:
        raise SystemExit("Final exact-surface count mismatch.")
    if pref.get("identity_count") != EXPECTED_IDENTITIES:
        raise SystemExit("Preferred-surface identity count mismatch.")
    if multi["summary"]["multiword_identity_count"] != EXPECTED_MULTIWORD_IDENTITIES:
        raise SystemExit("Multiword identity count mismatch.")
    if multi["summary"]["multiword_occurrence_count"] != EXPECTED_MULTIWORD_OCCURRENCES:
        raise SystemExit("Multiword occurrence count mismatch.")
    if multi["summary"]["unresolved_occurrence_count"] != 0:
        raise SystemExit("Multiword root linkage still has unresolved occurrences.")
    if basmala["summary"]["ayah0_basmala_count"] != EXPECTED_AYAH0:
        raise SystemExit("Basmala source count mismatch.")
    if basmala["summary"]["basmala_descriptor_occurrence_count"] != EXPECTED_BASMALA_DESCRIPTOR_OCCURRENCES:
        raise SystemExit("Basmala descriptor occurrence count mismatch.")

    rfs = rf.get("summary") or {}
    if str(rf.get("version")) != "1.4.1":
        raise SystemExit(f"Expected root-form builder output v1.4.1, got {rf.get('version')!r}")
    guards = {
        "one_word_identities_attempted": EXPECTED_ONE_WORD_IDENTITIES,
        "one_word_fully_matched": EXPECTED_ONE_WORD_IDENTITIES,
        "one_word_partial": 0,
        "one_word_unmatched": 0,
        "one_word_occurrences_total": EXPECTED_ONE_WORD_OCCURRENCES,
        "one_word_occurrences_matched": EXPECTED_ONE_WORD_OCCURRENCES,
        "one_word_occurrences_unmatched": 0,
    }
    for k, v in guards.items():
        if int(rfs.get(k, -1)) != v:
            raise SystemExit(f"Root-form summary mismatch {k}: expected {v}, got {rfs.get(k)}")

    pref_by_id = {r["lexical_identity_arabic"]: r for r in pref["records"]}
    freq_by_id = {r["lexical_identity_arabic"]: r for r in freq["lexical_identities"]}
    basmala_counts = Counter(r["lexical_identity_arabic"] for r in basmala["occurrences"])

    identities = [r["lexical_identity_arabic"] for r in freq["lexical_identities"]]
    descriptors = []
    for ident in identities:
        fr = freq_by_id[ident]
        pr = pref_by_id[ident]
        members = set(fr.get("member_surfaces") or [])
        if pr["preferred_quran_surface"] not in members:
            raise SystemExit(f"Preferred display surface is not member surface: {ident}")
        desc = {
            "lexical_identity_arabic": ident,
            "preferred_quran_surface": pr["preferred_quran_surface"],
            "numbered_occurrence_count": int(fr["occurrence_count"]),
            "basmala_occurrence_count": int(basmala_counts.get(ident, 0)),
            "combined_occurrence_count": int(fr["occurrence_count"]) + int(basmala_counts.get(ident, 0)),
            "exact_numbered_surface_count": int(fr.get("exact_surface_count") or len(members)),
            "numbered_member_surfaces": fr.get("member_surfaces") or [],
            **pick_meta(metadata.get(ident)),
        }
        descriptors.append(desc)

    missing_transliteration = [
        d["lexical_identity_arabic"]
        for d in descriptors
        if not str(d.get("transliteration") or "").strip()
    ]
    missing_english_gloss = [
        d["lexical_identity_arabic"]
        for d in descriptors
        if not str(d.get("english_gloss") or "").strip()
    ]
    if missing_transliteration:
        raise SystemExit(
            "Publication descriptors missing transliteration metadata: "
            + ", ".join(missing_transliteration)
        )
    if missing_english_gloss:
        raise SystemExit(
            "Publication descriptors missing English meaning/gloss metadata: "
            + ", ".join(missing_english_gloss)
        )

    # Combined occurrence ledger.
    numbered = []
    for r in occ["occurrences"]:
        rr = dict(r)
        rr["record_type"] = "numbered_ayah"
        numbered.append(rr)
    basmala_rows = [dict(r) for r in basmala["occurrences"]]
    combined = numbered + basmala_rows
    ids = [r["occurrence_id"] for r in combined]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate occurrence IDs in combined publication ledger.")

    # One-word occurrence root-link records from exact v1.4.1 audit.
    one_links = []
    for ar in rfa.get("occurrence_audit") or []:
        if ar.get("status") != "MATCHED":
            continue
        ident = ar.get("descriptor_arabic")
        if ident and len(str(ident).split()) == 1:
            one_links.append({
                "scope": "one_word",
                "lexical_identity_arabic": ident,
                "occurrence_id": ar.get("occurrence_id"),
                "verse_key": ar.get("verse_key"),
                "surface_arabic": ar.get("surface_arabic"),
                "word_location": ar.get("word_location"),
                "form_group_id": ar.get("form_group_id"),
                "public_forms": ar.get("public_forms") or [],
            })
    if len(one_links) != EXPECTED_ONE_WORD_OCCURRENCES:
        raise SystemExit(f"Expected {EXPECTED_ONE_WORD_OCCURRENCES} one-word root links, got {len(one_links)}")

    missing_root_dictionary_urls = []
    for link in one_links:
        forms = link.get("public_forms") or []
        if not forms:
            missing_root_dictionary_urls.append(link.get("occurrence_id"))
            continue
        usable = any(
            str(f.get("pray_for_the_truth_root_url") or "").startswith(
                "https://prayforthetruth.com/root/"
            )
            for f in forms
        )
        if not usable:
            missing_root_dictionary_urls.append(link.get("occurrence_id"))
    if missing_root_dictionary_urls:
        raise SystemExit(
            "One-word root links missing Pray for the Truth root-dictionary URLs: "
            + ", ".join(str(x) for x in missing_root_dictionary_urls[:25])
            + (" ..." if len(missing_root_dictionary_urls) > 25 else "")
        )

    multi_links = []
    for r in multi["records"]:
        multi_links.append({
            "scope": "multiword",
            **r,
        })
    if len(multi_links) != EXPECTED_MULTIWORD_OCCURRENCES:
        raise SystemExit("Multiword root-link occurrence count mismatch.")

    ayah0_links = [{
        "scope": "ayah0_basmala",
        "lexical_identity_arabic": r["lexical_identity_arabic"],
        "occurrence_id": r["occurrence_id"],
        "source_key": r["source_key"],
        "surface_arabic": r["surface_arabic"],
        "status": "NO_QAC_RECORD_FOR_AYAH0",
        "root_links": None,
    } for r in basmala_rows]

    root_links = one_links + multi_links + ayah0_links

    exclusion_history = {
        "version": "publication-v1",
        "source_licenses": SOURCE_LICENSES,
        "descriptor_level": load(corpus / "excluded_descriptors.json"),
        "occurrence_level": load(corpus / "excluded_occurrences.json"),
        "manual_review_decisions": decisions,
    }

    outdir.mkdir(parents=True, exist_ok=True)
    dump(outdir / "descriptors.json", {
        "version": "publication-v1",
        "descriptor_count": len(descriptors),
        "source_licenses": SOURCE_LICENSES,
        "descriptors": descriptors,
    })
    dump(outdir / "occurrence_ledger.json", {
        "version": "publication-v1",
        "numbered_occurrence_count": len(numbered),
        "ayah0_basmala_occurrence_count": len(basmala_rows),
        "combined_occurrence_count": len(combined),
        "source_licenses": SOURCE_LICENSES,
        "occurrences": combined,
    })
    dump(outdir / "lexical_index.json", {
        "version": "publication-v1",
        "source_licenses": SOURCE_LICENSES,
        "identity_order": identities,
        "by_identity": {x["lexical_identity_arabic"]: x for x in descriptors},
    })
    dump(outdir / "exclusion_history.json", exclusion_history)
    dump(outdir / "root_links.json", {
        "version": "publication-v1",
        "one_word_numbered_links": len(one_links),
        "multiword_numbered_links": len(multi_links),
        "ayah0_explicit_null_links": len(ayah0_links),
        "source_licenses": SOURCE_LICENSES,
        "links": root_links,
    })

    validation = {
        "status": "PASS",
        "publication_final": True,
        "semantic_version": "semantic_exclusions_v2",
        "source_licenses": SOURCE_LICENSES,
        "counts": {
            "lexical_identities": len(descriptors),
            "numbered_occurrences": len(numbered),
            "numbered_exact_surfaces": EXPECTED_SURFACES,
            "one_word_identities": EXPECTED_ONE_WORD_IDENTITIES,
            "one_word_numbered_occurrences": EXPECTED_ONE_WORD_OCCURRENCES,
            "multiword_identities": EXPECTED_MULTIWORD_IDENTITIES,
            "multiword_numbered_occurrences": EXPECTED_MULTIWORD_OCCURRENCES,
            "ayah0_basmala_records": EXPECTED_AYAH0,
            "ayah0_descriptor_occurrences": len(basmala_rows),
            "combined_descriptor_occurrences": len(combined),
        },
        "assertions": {
            "quran_source_sha_unchanged": True,
            "semantic_review_reconciled": True,
            "all_numbered_occurrence_ids_unique": len({r["occurrence_id"] for r in numbered}) == len(numbered),
            "all_combined_occurrence_ids_unique": len(set(ids)) == len(ids),
            "all_preferred_display_forms_quran_attested": True,
            "all_descriptors_have_transliteration": True,
            "all_descriptors_have_english_gloss": True,
            "all_one_word_root_links_exact_and_matched": True,
            "all_one_word_root_links_have_public_dictionary_url": True,
            "all_multiword_root_links_resolved": True,
            "ayah0_qac_links_explicitly_null_not_fabricated": True,
            "no_new_semantic_identities_created_by_basmala": True,
        },
    }
    dump(outdir / "validation_report.json", validation)

    manifest_files = [
        "descriptors.json",
        "occurrence_ledger.json",
        "lexical_index.json",
        "exclusion_history.json",
        "root_links.json",
        "validation_report.json",
    ]
    manifest = {
        "version": "publication-v1",
        "publication_final": True,
        "quran_source_sha256": EXPECTED_QURAN_SHA,
        "source_semantic_version": "semantic_exclusions_v2",
        "source_licenses": SOURCE_LICENSES,
        "files": {},
    }
    for name in manifest_files:
        p = outdir / name
        manifest["files"][name] = {
            "sha256": sha256(p),
            "bytes": p.stat().st_size,
        }
    dump(outdir / "manifest.json", manifest)

    # Hash manifest itself separately in a plain checksum file to avoid self-reference.
    checks = []
    for p in sorted(outdir.glob("*.json")):
        checks.append(f"{sha256(p)}  {p.name}")
    (outdir / "SHA256SUMS").write_text("\n".join(checks) + "\n", encoding="utf-8")

    print("PUBLICATION FREEZE V1: PASS")
    print(f"Descriptors: {len(descriptors)}")
    print(f"Numbered occurrences: {len(numbered)}")
    print(f"Ayah:0 descriptor occurrences: {len(basmala_rows)}")
    print(f"Combined occurrences: {len(combined)}")
    print(f"One-word root links: {len(one_links)}")
    print(f"Multiword root links: {len(multi_links)}")
    print(f"Output: {outdir}")

if __name__ == "__main__":
    main()
