#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED = {
    "lexical_identities": 225,
    "numbered_occurrences": 5037,
    "combined_descriptor_occurrences": 5373,
}

REQUIRED = [
    "README.md",
    "LICENSE",
    "LICENSE_SCOPE.md",
    "THIRD_PARTY_NOTICES.md",
    "PUBLIC_RELEASE.json",
    ".nojekyll",
    "index.html",
    "assets/app.js",
    "assets/styles.css",
    "data/descriptors.json",
    "data/occurrence_ledger.json",
    "data/lexical_index.json",
    "data/exclusion_history.json",
    "data/root_links.json",
    "data/manifest.json",
    "data/validation_report.json",
    "data/SHA256SUMS",
    "data/DATA_LICENSE.md",
    "docs/LICENSING.md",
    "docs/SOURCE_PROVENANCE.md",
    "docs/PUBLIC_RELEASE_BOUNDARY.md",
]

FORBIDDEN_DATA_KEYS = {
    "context_gloss",
    "quran_foundation_translation",
    "quran_foundation_transliteration",
    "qf_translation",
    "qf_transliteration",
    "english_verse_translation",
}


def walk_keys(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_DATA_KEYS:
                found.add(k)
            walk_keys(v, found)
    elif isinstance(obj, list):
        for x in obj:
            walk_keys(x, found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path)
    a = ap.parse_args()
    target = a.target.expanduser().resolve()

    missing = [p for p in REQUIRED if not (target / p).exists()]
    if missing:
        raise SystemExit("Missing required public-release files:\n  " + "\n  ".join(missing))

    validation = json.loads((target / "data/validation_report.json").read_text(encoding="utf-8"))
    if validation.get("status") != "PASS" or validation.get("publication_final") is not True:
        raise SystemExit("Publication validation is not PASS/publication_final.")
    counts = validation.get("counts") or {}
    for k, v in EXPECTED.items():
        if int(counts.get(k, -1)) != v:
            raise SystemExit(f"Count mismatch {k}: expected {v}, got {counts.get(k)}")

    descriptors_doc = json.loads(
        (target / "data/descriptors.json").read_text(encoding="utf-8")
    )
    descriptors = descriptors_doc.get("descriptors") or []
    if len(descriptors) != EXPECTED["lexical_identities"]:
        raise SystemExit(
            f"descriptors.json count mismatch: expected {EXPECTED['lexical_identities']}, got {len(descriptors)}"
        )

    missing_transliteration = [
        d.get("lexical_identity_arabic")
        for d in descriptors
        if not str(d.get("transliteration") or "").strip()
    ]
    missing_gloss = [
        d.get("lexical_identity_arabic")
        for d in descriptors
        if not str(d.get("english_gloss") or "").strip()
    ]
    if missing_transliteration:
        raise SystemExit(
            "Descriptors missing transliteration: "
            + ", ".join(str(x) for x in missing_transliteration)
        )
    if missing_gloss:
        raise SystemExit(
            "Descriptors missing English meaning/gloss: "
            + ", ".join(str(x) for x in missing_gloss)
        )

    root_doc = json.loads(
        (target / "data/root_links.json").read_text(encoding="utf-8")
    )
    one_word_links = [
        x for x in (root_doc.get("links") or [])
        if x.get("scope") == "one_word"
    ]
    if len(one_word_links) != 4798:
        raise SystemExit(
            f"One-word root-link count mismatch: expected 4798, got {len(one_word_links)}"
        )

    bad_root_urls = []
    for link in one_word_links:
        forms = link.get("public_forms") or []
        if not forms or not any(
            str(f.get("pray_for_the_truth_root_url") or "").startswith(
                "https://prayforthetruth.com/root/"
            )
            for f in forms
        ):
            bad_root_urls.append(link.get("occurrence_id"))
    if bad_root_urls:
        raise SystemExit(
            "One-word root links missing public root-dictionary URL: "
            + ", ".join(str(x) for x in bad_root_urls[:25])
            + (" ..." if len(bad_root_urls) > 25 else "")
        )

    release = json.loads((target / "PUBLIC_RELEASE.json").read_text(encoding="utf-8"))
    if release.get("quran_foundation_raw_content_included") is not False:
        raise SystemExit("Public release marker does not explicitly exclude QF raw content.")

    found = set()
    for p in (target / "data").glob("*.json"):
        walk_keys(json.loads(p.read_text(encoding="utf-8")), found)
    if found:
        raise SystemExit(f"Forbidden QF/translation-style keys found in public data: {sorted(found)}")

    html = (target / "index.html").read_text(encoding="utf-8")
    js = (target / "assets/app.js").read_text(encoding="utf-8")
    for required_ref in ("./assets/styles.css", "./assets/app.js"):
        if required_ref not in html:
            raise SystemExit(f"Pages viewer missing reference: {required_ref}")
    for required_fetch in (
        "./data/descriptors.json",
        "./data/occurrence_ledger.json",
        "./data/root_links.json",
        "./data/validation_report.json",
    ):
        if required_fetch not in js:
            raise SystemExit(f"Pages viewer does not fetch required publication file: {required_fetch}")

    for required_ui_token in (
        "english_gloss",
        "pray_for_the_truth_root_url",
        "Open full root dictionary",
        "Root dictionary",
        "Roots in this phrase",
    ):
        if required_ui_token not in js and required_ui_token not in html:
            raise SystemExit(
                f"Pages viewer missing required usability token: {required_ui_token}"
            )

    for forbidden_viewer_token in (
        "./docs/METHOD_AND_FREEZE.md",
        ">Validation</a>",
        ">Method</a>",
        ">License</a>",
        "No traditional 99 Names list was used as a seed or checklist.",
        'class="method-banner"',
        "Technical identifiers",
        "QAC word location:",
        "QAC form-group ID:",
        "Quran Roots public-form ID:",
        'class="root-evidence"',
    ):
        if forbidden_viewer_token in html or forbidden_viewer_token in js:
            raise SystemExit(
                f"Pages viewer contains removed documentation/method UI: {forbidden_viewer_token}"
            )

    readme = (target / "README.md").read_text(encoding="utf-8")
    for phrase in (
        "Quran-only, text-first research corpus",
        "was **not** supplied as a seed",
        "Why “descriptors”?",
        "English meaning/gloss for every descriptor",
        "full Quran Roots Dictionary",
    ):
        if phrase not in readme:
            raise SystemExit(f"README missing core project framing/usability text: {phrase}")

    license_scope = (target / "LICENSE_SCOPE.md").read_text(encoding="utf-8")
    for phrase in ("GPL-3.0-only", "Important QAC limitation", "Quran Foundation boundary"):
        if phrase not in license_scope:
            raise SystemExit(f"LICENSE_SCOPE missing expected section/text: {phrase}")

    print("PUBLIC RELEASE VALIDATION: PASS")
    print(f"Target: {target}")
    print("Descriptors: 225")
    print("Numbered occurrences: 5037")
    print("Combined occurrences: 5373")
    print("GitHub Pages viewer: present")
    print("Descriptor transliterations: 225/225")
    print("Descriptor English meanings: 225/225")
    print("One-word root dictionary links: 4798/4798")
    print("README Quran-only / no-99-Names-seed framing: present")
    print("Viewer documentation/method utility links: intentionally absent")
    print("Per-occurrence root/morphology blocks: absent")
    print("Technical identifiers in viewer UI: absent")
    print("Descriptor-level root dictionary navigation: present")
    print("GPL LICENSE + layered license scope: present")
    print("QF raw/API payload keys: none detected")


if __name__ == "__main__":
    main()
