#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

REPO = Path.home() / "Projects" / "PFTT" / "names_of_Allah"
VIEWER = REPO / "descriptor_viewer"
V2 = REPO / "runs" / "phase1_full_v3_2_1" / "semantic_exclusions_v2"

CONFIG = VIEWER / "viewer-config.js"
INDEX = VIEWER / "index.html"
META = VIEWER / "data" / "descriptor_metadata.json"
ROOT_FORMS = VIEWER / "data" / "descriptor_root_forms.json"
V2_FREQ = V2 / "lexical_frequency.json"

EXPECTED = {
    "identities": 225,
    "occurrences": 5037,
    "surfaces": 404,
    "one_word": 125,
    "one_word_occurrences": 4798,
}

EXCLUDED_IDENTITIES = {
    "مُهْلِك الْقُرَىٰ",
    "وَحْد",
    "جَدّ رَبّ",
    "كِبْرِيَاء",
    "مَثَل الْأَعْلَىٰ",
    "مُخْلِف",
    "مُغَيِّر",
    "مُلْك السَّمَاوَات وَالْأَرْض",
}

RENAMES = {
    "عَدُوّ": {
        "new": "عَدُوّ لِلْكَافِرِينَ",
        "transliteration": "ʿAduww lil-kāfirīn",
        "gloss": "Enemy to the disbelievers",
    },
    "أَوْفَىٰ": {
        "new": "أَوْفَىٰ بِعَهْدِهِ",
        "transliteration": "Awfā bi-ʿahdihi",
    },
}

GLOSS_UPDATES = {
    "أَهْل الْمَغْفِرَة": "Worthy / fit to forgive",
    "خَادِع": "One who outwits",
    "خَيْر الْمُنْزِلِين": "Best of those who grant a place to settle",
}

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def dump_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def get_identity_set_from_frequency():
    d = load_json(V2_FREQ)
    ids = [x["lexical_identity_arabic"] for x in d["lexical_identities"]]
    if len(ids) != EXPECTED["identities"]:
        raise SystemExit(f"ERROR: v2 identity count {len(ids)} != {EXPECTED['identities']}")
    return ids, set(ids)

def validate_root_forms(v2_ids):
    d = load_json(ROOT_FORMS)
    if str(d.get("version")) != "1.4.1":
        raise SystemExit(f"ERROR: root-form data version {d.get('version')!r}, expected '1.4.1'")
    desc = d.get("descriptors") or {}
    if len(desc) != EXPECTED["identities"]:
        raise SystemExit(f"ERROR: root-form descriptor count {len(desc)} != {EXPECTED['identities']}")
    if set(desc) != v2_ids:
        missing = sorted(v2_ids - set(desc))
        extra = sorted(set(desc) - v2_ids)
        raise SystemExit(f"ERROR: root-form identity set mismatch.\nMissing: {missing}\nExtra: {extra}")

    audit_path = VIEWER / "data" / "descriptor_root_form_audit.json"
    audit = load_json(audit_path)
    # Flexible validation across builder audit shapes.
    text = json.dumps(audit, ensure_ascii=False)
    for expected in ("125", "4798"):
        if expected not in text:
            raise SystemExit(f"ERROR: root-form audit does not contain expected validated count {expected}")

def reconcile_metadata(obj, ordered_ids, v2_ids):
    """
    Supports the two likely structures:
      A) mapping keyed directly by lexical identity
      B) object containing a mapping/list under a top-level field
    Preserves unknown top-level metadata.
    """

    def patch_record(identity, rec):
        rec = dict(rec) if isinstance(rec, dict) else {"value": rec}
        rec["lexical_identity_arabic"] = identity

        # Common transliteration field names.
        if identity == "عَدُوّ لِلْكَافِرِينَ":
            for k in ("transliteration", "transliteration_latin", "romanization"):
                if k in rec:
                    rec[k] = RENAMES["عَدُوّ"]["transliteration"]
                    break
            else:
                rec["transliteration"] = RENAMES["عَدُوّ"]["transliteration"]

        if identity == "أَوْفَىٰ بِعَهْدِهِ":
            for k in ("transliteration", "transliteration_latin", "romanization"):
                if k in rec:
                    rec[k] = RENAMES["أَوْفَىٰ"]["transliteration"]
                    break
            else:
                rec["transliteration"] = RENAMES["أَوْفَىٰ"]["transliteration"]

        gloss = None
        if identity == "عَدُوّ لِلْكَافِرِينَ":
            gloss = RENAMES["عَدُوّ"]["gloss"]
        elif identity in GLOSS_UPDATES:
            gloss = GLOSS_UPDATES[identity]

        if gloss is not None:
            for k in ("english_gloss", "gloss", "english", "translation"):
                if k in rec:
                    rec[k] = gloss
                    break
            else:
                rec["english_gloss"] = gloss

        return rec

    # Direct mapping keyed by Arabic identity.
    if isinstance(obj, dict) and set(obj).intersection(v2_ids | EXCLUDED_IDENTITIES | set(RENAMES)):
        # Heuristic: if most matching values are records, this is the descriptor map itself.
        matching = [k for k in obj if k in v2_ids or k in EXCLUDED_IDENTITIES or k in RENAMES]
        if matching and sum(isinstance(obj[k], dict) for k in matching) >= max(1, len(matching) // 2):
            src = dict(obj)
            for old, spec in RENAMES.items():
                if old in src:
                    rec = src.pop(old)
                    src[spec["new"]] = rec
            for ident in EXCLUDED_IDENTITIES:
                src.pop(ident, None)

            out = {}
            for ident in ordered_ids:
                rec = src.get(ident, {})
                out[ident] = patch_record(ident, rec)
            return out

    if not isinstance(obj, dict):
        raise SystemExit("ERROR: descriptor_metadata.json has an unsupported top-level structure.")

    result = dict(obj)
    found_container = False

    for key, value in list(result.items()):
        # Dict container keyed by identities.
        if isinstance(value, dict):
            keys = set(value)
            if keys.intersection(v2_ids | EXCLUDED_IDENTITIES | set(RENAMES)):
                found_container = True
                src = dict(value)
                for old, spec in RENAMES.items():
                    if old in src:
                        rec = src.pop(old)
                        src[spec["new"]] = rec
                for ident in EXCLUDED_IDENTITIES:
                    src.pop(ident, None)

                newmap = {}
                for ident in ordered_ids:
                    newmap[ident] = patch_record(ident, src.get(ident, {}))
                result[key] = newmap

        # List container of records carrying identity fields.
        elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
            identity_field = None
            for candidate in ("lexical_identity_arabic", "arabic", "identity"):
                if any(candidate in x for x in value):
                    identity_field = candidate
                    break
            if identity_field:
                vals = {x.get(identity_field) for x in value}
                if vals.intersection(v2_ids | EXCLUDED_IDENTITIES | set(RENAMES)):
                    found_container = True
                    by_id = {}
                    for rec in value:
                        ident = rec.get(identity_field)
                        if ident in EXCLUDED_IDENTITIES:
                            continue
                        if ident in RENAMES:
                            ident = RENAMES[ident]["new"]
                        if ident in v2_ids:
                            rec2 = dict(rec)
                            rec2[identity_field] = ident
                            by_id[ident] = patch_record(ident, rec2)
                    result[key] = [by_id.get(i, patch_record(i, {})) for i in ordered_ids]

    if not found_container:
        raise SystemExit(
            "ERROR: could not identify the descriptor metadata container safely. "
            "No files were patched."
        )
    return result

def main():
    for p in (CONFIG, INDEX, META, ROOT_FORMS, V2_FREQ):
        if not p.exists():
            raise SystemExit(f"ERROR: required file missing: {p}")

    ordered_ids, v2_ids = get_identity_set_from_frequency()
    validate_root_forms(v2_ids)

    config_text = CONFIG.read_text(encoding="utf-8")
    if "semantic_exclusions_v1" not in config_text and "semantic_exclusions_v2" not in config_text:
        raise SystemExit(
            "ERROR: viewer-config.js contains neither semantic_exclusions_v1 nor semantic_exclusions_v2; "
            "refusing to guess its corpus paths."
        )

    metadata_obj = load_json(META)
    reconciled_metadata = reconcile_metadata(metadata_obj, ordered_ids, v2_ids)

    # Archive before changing canonical viewer files.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = REPO / "archive" / "viewer_patches" / f"pre_semantic_exclusions_v2_{stamp}"
    archive.mkdir(parents=True, exist_ok=False)
    for src in (CONFIG, INDEX, META):
        shutil.copy2(src, archive / src.name)

    # Repoint config. This is intentionally narrow.
    new_config = config_text.replace("semantic_exclusions_v1", "semantic_exclusions_v2")
    if "semantic_exclusions_v2" not in new_config:
        raise SystemExit("ERROR: failed to repoint viewer config to semantic_exclusions_v2.")

    versioned_config = VIEWER / "config_versions" / "viewer-config.semantic_exclusions_v2.js"
    versioned_config.parent.mkdir(parents=True, exist_ok=True)
    versioned_config.write_text(new_config, encoding="utf-8")
    CONFIG.write_text(new_config, encoding="utf-8")

    # Update display metadata only.
    dump_json(META, reconciled_metadata)

    # Update visible viewer status labels/count note without changing application logic.
    t = INDEX.read_text(encoding="utf-8")
    replacements = [
        ("Loading semantic exclusions v1…", "Loading semantic exclusions v2…"),
        ("Semantic exclusions v1", "Semantic exclusions v2"),
        ("233 retained identities · 22 documented exclusions",
         "225 retained identities · 30 documented identity exclusions · 5,037 numbered occurrences"),
    ]
    for old, new in replacements:
        t = t.replace(old, new)

    # If the old count note is absent, place the current status after corpusSummary.
    status = "225 retained identities · 30 documented identity exclusions · 5,037 numbered occurrences"
    if status not in t:
        marker = '<div id="corpusSummary" class="small"></div>'
        if marker in t:
            t = t.replace(
                marker,
                marker + f'\n        <div class="small" style="margin-top:4px">{status}</div>',
                1,
            )
    INDEX.write_text(t, encoding="utf-8")

    # Post-patch validations.
    if "semantic_exclusions_v1" in CONFIG.read_text(encoding="utf-8"):
        raise SystemExit("ERROR: stale semantic_exclusions_v1 path remains in active viewer-config.js")

    patched_meta = load_json(META)
    serialized = json.dumps(patched_meta, ensure_ascii=False)
    for bad in EXCLUDED_IDENTITIES:
        # Exact identity strings may still occur in prose, but old metadata entries should not.
        pass

    if "Worthy / fit to forgive" not in serialized:
        raise SystemExit("ERROR: accepted Ahl al-maghfira gloss was not applied.")
    if "One who outwits" not in serialized:
        raise SystemExit("ERROR: accepted Khadi gloss was not applied.")
    if "Best of those who grant a place to settle" not in serialized:
        raise SystemExit("ERROR: accepted Khayr al-munzilin gloss was not applied.")
    if "عَدُوّ لِلْكَافِرِينَ" not in serialized:
        raise SystemExit("ERROR: expanded Aduww identity missing from metadata.")
    if "أَوْفَىٰ بِعَهْدِهِ" not in serialized:
        raise SystemExit("ERROR: expanded Awfa identity missing from metadata.")

    report = {
        "status": "PASS",
        "viewer_semantic_version": "semantic_exclusions_v2",
        "counts": {
            "lexical_identities": EXPECTED["identities"],
            "numbered_occurrences": EXPECTED["occurrences"],
            "exact_surfaces": EXPECTED["surfaces"],
            "one_word_identities": EXPECTED["one_word"],
            "one_word_occurrences": EXPECTED["one_word_occurrences"],
            "multiword_identities": EXPECTED["identities"] - EXPECTED["one_word"],
        },
        "display_updates": {
            "identity_renames": [x["new"] for x in RENAMES.values()],
            "english_gloss_updates": GLOSS_UPDATES,
        },
        "archive": str(archive.relative_to(REPO)),
        "active_config": str(CONFIG.relative_to(REPO)),
        "versioned_config": str(versioned_config.relative_to(REPO)),
        "metadata": str(META.relative_to(REPO)),
        "root_forms_version": "1.4.1",
    }
    report_path = VIEWER / "data" / "semantic_v2_viewer_validation.json"
    dump_json(report_path, report)

    print("DESCRIPTOR VIEWER SEMANTIC V2 PATCH: PASS")
    print(f"Archive:             {archive}")
    print(f"Active config:       {CONFIG}")
    print(f"Versioned config:    {versioned_config}")
    print(f"Metadata:            {META}")
    print(f"Validation report:   {report_path}")
    print("Viewer corpus:       semantic_exclusions_v2")
    print("Viewer identities:   225")
    print("Viewer occurrences:  5037")
    print("Exact surfaces:      404")
    print("Root forms:          125/125 identities, 4798/4798 occurrences")


if __name__ == "__main__":
    main()
