#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

VERSION = "1.1"

EXPECTED_IDENTITIES = 225
EXPECTED_MULTIWORD_IDENTITIES = 100
EXPECTED_MULTIWORD_OCCURRENCES = 239

ARABIC_COMBINING_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def token_has_letter(token: str) -> bool:
    return any(unicodedata.category(ch).startswith("L") for ch in token)


def lexical_token_spans(text: str):
    out = []
    pos = 0
    for m in re.finditer(r"\S+", text):
        tok = m.group(0)
        if not token_has_letter(tok):
            continue
        pos += 1
        out.append((m.start(), m.end(), tok, pos))
    return out


def normalize(text: str) -> str:
    s = ARABIC_COMBINING_RE.sub("", str(text or "")).replace("ـ", "")
    s = (
        s.replace("ٱ", "ا")
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
    )
    return "".join(
        ch for ch in s
        if unicodedata.category(ch).startswith("L")
    )


def root_arabic(root):
    return root.get("root_arabic") or root.get("arabic")


def build_form_group_index(form_inventory):
    by_segment = {}
    groups = {}

    for root in form_inventory.get("roots", []):
        for form in root.get("forms", []):
            gid = form.get("form_group_id")
            if not gid:
                continue

            summary = {
                "form_group_id": gid,
                "root": root.get("root"),
                "root_arabic": root.get("arabic"),
                "lexical_class": form.get("lexical_class"),
                "qac_lemma_arabic": (
                    (form.get("qac_lemma") or {}).get("arabic")
                    or form.get("qac_lemma_arabic_candidate")
                ),
                "public_morphology_hint": form.get("public_morphology_hint"),
                "verb_form": form.get("verb_form"),
            }
            groups[gid] = summary

            for oc in form.get("occurrences", []):
                seg = oc.get("segment_location")
                if not seg:
                    continue
                if seg in by_segment and by_segment[seg]["form_group_id"] != gid:
                    raise SystemExit(
                        f"Segment assigned to multiple form groups: {seg}"
                    )
                by_segment[seg] = summary

    return by_segment, groups


def get_overlap_tokens(occ):
    start = int(occ["start_offset"])
    end = int(occ["end_offset"])

    out = []
    for ts, te, tok, pos in lexical_token_spans(occ["verse_text"]):
        os = max(ts, start)
        oe = min(te, end)
        if os < oe:
            fragment = occ["verse_text"][os:oe]
            if token_has_letter(fragment):
                out.append({
                    "verse_token_position": pos,
                    "verse_token": tok,
                    "descriptor_fragment": fragment,
                    "fragment_start_offset": os,
                    "fragment_end_offset": oe,
                })
    return out


def validate_fragment_against_word(fragment, word):
    fn = normalize(fragment)
    if not fn:
        return False

    candidates = [
        normalize(word.get("arabic_imlaei")),
        normalize(word.get("arabic_uthmani")),
    ]

    return any(
        c and (fn == c or fn in c or c in fn)
        for c in candidates
    )


def get_word(words, word_location):
    word = words.get(word_location)
    return word if isinstance(word, dict) else None


def window_matches(tokens, window_locations, words):
    if len(tokens) != len(window_locations):
        return False

    for token, word_location in zip(tokens, window_locations):
        word = get_word(words, word_location)
        if word is None:
            return False
        if not validate_fragment_against_word(
            token["descriptor_fragment"],
            word,
        ):
            return False

    return True


def resolve_word_locations(tokens, word_order, words):
    n = len(tokens)

    if n == 0:
        return None, {"code": "NO_DESCRIPTOR_TOKENS"}

    positions = [t["verse_token_position"] for t in tokens]

    if positions == list(range(positions[0], positions[0] + n)):
        start_idx = positions[0] - 1
        end_idx = start_idx + n

        if 0 <= start_idx < len(word_order) and end_idx <= len(word_order):
            positional_window = word_order[start_idx:end_idx]

            if window_matches(tokens, positional_window, words):
                return positional_window, {
                    "alignment_method": "SOURCE_OFFSET_ABSOLUTE_POSITION",
                    "candidate_count": 1,
                }

    matches = []

    for start_idx in range(0, len(word_order) - n + 1):
        window = word_order[start_idx:start_idx + n]

        if window_matches(tokens, window, words):
            matches.append(window)

    if len(matches) == 1:
        return matches[0], {
            "alignment_method": "UNIQUE_CONTIGUOUS_SURFACE_SEQUENCE",
            "candidate_count": 1,
        }

    if not matches:
        return None, {
            "code": "NO_VALID_CONTIGUOUS_WORD_WINDOW",
            "candidate_count": 0,
            "descriptor_fragments": [
                t["descriptor_fragment"] for t in tokens
            ],
        }

    return None, {
        "code": "AMBIGUOUS_CONTIGUOUS_WORD_WINDOW",
        "candidate_count": len(matches),
        "candidate_windows": matches,
        "descriptor_fragments": [
            t["descriptor_fragment"] for t in tokens
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    ap.add_argument("--quran-roots", type=Path)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    repo = a.repo.resolve()
    qroots = (
        a.quran_roots
        or (repo.parent / "SOURCES/quran-roots")
    ).resolve()

    corpus = (
        repo
        / "runs/phase1_full_v3_2_1/semantic_exclusions_v2"
    )
    out = (
        repo
        / "runs/phase1_full_v3_2_1/finalization_v1/"
          "multiword_root_links.json"
    )

    if out.exists() and not a.overwrite:
        raise SystemExit(
            f"Refusing to overwrite existing output: {out}"
        )

    occurrences = load(
        corpus / "descriptor_occurrences_lexical.json"
    )["occurrences"]
    freq = load(
        corpus / "lexical_frequency.json"
    )["lexical_identities"]
    form_inventory = load(
        qroots / "output/quran_form_inventory_v1.json"
    )

    form_by_segment, _ = build_form_group_index(
        form_inventory
    )

    identities = [
        x["lexical_identity_arabic"]
        for x in freq
    ]

    if len(identities) != EXPECTED_IDENTITIES:
        raise SystemExit(
            f"Expected {EXPECTED_IDENTITIES} identities, "
            f"got {len(identities)}"
        )

    multi_ids = [
        x for x in identities
        if len(x.split()) > 1
    ]
    multi_set = set(multi_ids)

    multi_rows = [
        x for x in occurrences
        if x["lexical_identity_arabic"] in multi_set
    ]

    if len(multi_ids) != EXPECTED_MULTIWORD_IDENTITIES:
        raise SystemExit(
            f"Expected {EXPECTED_MULTIWORD_IDENTITIES} "
            f"multiword identities, got {len(multi_ids)}"
        )

    if len(multi_rows) != EXPECTED_MULTIWORD_OCCURRENCES:
        raise SystemExit(
            f"Expected {EXPECTED_MULTIWORD_OCCURRENCES} "
            f"multiword occurrences, got {len(multi_rows)}"
        )

    surah_cache = {}
    records = []
    unresolved = []
    alignment_counts = Counter()

    for idx, occ in enumerate(multi_rows, 1):
        surah = int(
            str(occ["verse_key"]).split(":")[0]
        )

        if surah not in surah_cache:
            p = (
                qroots
                / "output/quran_app_dataset_v2/word_analysis"
                / f"{surah:03d}.json"
            )
            surah_cache[surah] = load(p)

        sd = surah_cache[surah]
        verse = (
            (sd.get("verses_by_key") or {})
            .get(occ["verse_key"])
        )

        if not isinstance(verse, dict):
            unresolved.append({
                "occurrence_id": occ["occurrence_id"],
                "code": "VERSE_NOT_FOUND",
            })
            continue

        word_order = verse.get("word_order") or []
        words = verse.get("words_by_location") or {}
        tokens = get_overlap_tokens(occ)

        if len(tokens) < 2:
            unresolved.append({
                "occurrence_id": occ["occurrence_id"],
                "code": "MULTIWORD_SPAN_HAS_LT2_TOKENS",
                "tokens": tokens,
            })
            continue

        resolved_locations, alignment = resolve_word_locations(
            tokens,
            word_order,
            words,
        )

        if resolved_locations is None:
            unresolved.append({
                "occurrence_id": occ["occurrence_id"],
                "verse_key": occ["verse_key"],
                "surface_arabic": occ["surface_arabic"],
                **alignment,
            })
            continue

        alignment_counts[
            alignment["alignment_method"]
        ] += 1

        constituent_words = []
        ok = True

        for token, word_location in zip(
            tokens,
            resolved_locations,
        ):
            word = get_word(words, word_location)

            if word is None:
                unresolved.append({
                    "occurrence_id": occ["occurrence_id"],
                    "code": "WORD_LOCATION_NOT_FOUND",
                    "word_location": word_location,
                })
                ok = False
                break

            if not validate_fragment_against_word(
                token["descriptor_fragment"],
                word,
            ):
                unresolved.append({
                    "occurrence_id": occ["occurrence_id"],
                    "code": "RESOLVED_WORD_TEXT_VALIDATION_FAILED",
                    "word_location": word_location,
                    "descriptor_fragment": token["descriptor_fragment"],
                    "arabic_imlaei": word.get("arabic_imlaei"),
                    "arabic_uthmani": word.get("arabic_uthmani"),
                })
                ok = False
                break

            roots_out = []

            for root in word.get("roots") or []:
                segs = list(
                    root.get("segment_locations") or []
                )
                forms = []

                for seg in segs:
                    fg = form_by_segment.get(seg)

                    if fg is None:
                        unresolved.append({
                            "occurrence_id": occ["occurrence_id"],
                            "code": "ROOT_SEGMENT_MISSING_FORM_GROUP",
                            "word_location": word_location,
                            "segment_location": seg,
                            "root": root.get("root"),
                        })
                        ok = False
                        break

                    forms.append(fg)

                if not ok:
                    break

                roots_out.append({
                    "root": root.get("root"),
                    "root_id": root.get("root_id"),
                    "root_arabic": root_arabic(root),
                    "dictionary_path": root.get("dictionary_path"),
                    "segment_locations": segs,
                    "form_groups": forms,
                })

            if not ok:
                break

            constituent_words.append({
                **token,
                "resolved_word_location": word_location,
                "arabic_imlaei": word.get("arabic_imlaei"),
                "arabic_uthmani": word.get("arabic_uthmani"),
                "roots": roots_out,
            })

        if not ok:
            continue

        records.append({
            "lexical_identity_arabic": occ["lexical_identity_arabic"],
            "occurrence_id": occ["occurrence_id"],
            "verse_key": occ["verse_key"],
            "surface_arabic": occ["surface_arabic"],
            "start_offset": occ["start_offset"],
            "end_offset": occ["end_offset"],
            "status": "LINKED",
            "alignment_method": alignment["alignment_method"],
            "constituent_words": constituent_words,
        })

        if idx % 25 == 0:
            print(
                f"  processed {idx}/{len(multi_rows)} "
                "multiword occurrences"
            )

    output = {
        "version": "multiword-root-links-v1.1",
        "builder_version": VERSION,
        "source_semantic_version": "semantic-exclusions-v2",
        "join_contract": (
            "descriptor verse_key + exact source offsets -> source lexical-token sequence; "
            "first try absolute source token position against word_analysis.word_order; "
            "if that fails validation, require a unique contiguous same-verse Quran-surface "
            "sequence match -> stable word_location IDs -> existing QAC root segment locations "
            "-> quran_form_inventory exact form_group_id"
        ),
        "policy": {
            "semantic_identity_remains_whole": True,
            "roots_inferred_from_spelling": False,
            "fallback_is_same_verse_contiguous_sequence_only": True,
            "fallback_requires_unique_match": True,
            "quran_text_normalization_used_only_for_word_alignment": True,
            "rootless_constituent_words_allowed": True,
        },
        "summary": {
            "multiword_identity_count": len(multi_ids),
            "multiword_occurrence_count": len(multi_rows),
            "linked_occurrence_count": len(records),
            "unresolved_occurrence_count": len(unresolved),
            "alignment_method_counts": dict(
                sorted(alignment_counts.items())
            ),
        },
        "records": records,
        "unresolved": unresolved,
    }

    dump(out, output)

    if unresolved:
        print("MULTIWORD ROOT LINKAGE: REVIEW REQUIRED")
        print(f"Builder version: {VERSION}")
        print(f"Linked: {len(records)}/{len(multi_rows)}")
        print(f"Unresolved: {len(unresolved)}")
        print(
            "Alignment methods: "
            + json.dumps(dict(alignment_counts), ensure_ascii=False)
        )
        print(f"Output: {out}")
        raise SystemExit(2)

    print("MULTIWORD ROOT LINKAGE: PASS")
    print(f"Builder version: {VERSION}")
    print(f"Identities: {len(multi_ids)}")
    print(
        f"Occurrences linked: "
        f"{len(records)}/{len(multi_rows)}"
    )
    print(
        "Alignment methods: "
        + json.dumps(dict(alignment_counts), ensure_ascii=False)
    )
    print(f"Output: {out}")


if __name__ == "__main__":
    main()
