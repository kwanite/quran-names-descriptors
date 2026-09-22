# Root-form builder v1.4 — exact QAC occurrence/form patch

**Date:** 2026-09-13  
**Status:** replaces builder v1.3 for viewer morphology enrichment

## Problem

Builder v1.3 used the reviewed abstract lexical identity as a guard against the QAC lemma. That prevented catastrophic wrong-root matches, but it was too strict because the QAC lemma is an internal morphology identity and can preserve Quranic spelling, inflection, plural morphology, or a corpus-specific lemma that differs from the Names project's normalized lexical identity.

This produced false unmatched results for obvious retained descriptors such as `ظَاهِر` and `سَلَام`.

## Decision

Version 1.4 chooses the root-dictionary form from the **exact form expressed at the retained Quran occurrence**:

```text
Names occurrence exact Quran surface
    -> exact QAC root-bearing surface in the same verse
    -> exact QAC segment_location
    -> exact QAC form_group_id
    -> final v8 quranic_form
    -> public_pos_label / public headword / root_id
```

The abstract Names lexical identity is no longer used to select or reject the QAC form.

## Why this is safer

The QAC form inventory already records every root-bearing Quran occurrence with:

- `verse_key`
- `word_location`
- `segment_location`
- `surface_arabic`
- `form_group_id`
- root identity
- morphology

Therefore there is no need to infer a form from the lexical identity or rely on possibly misaligned Quran Foundation word records.

## Surface comparison normalization

Normalization is limited to cross-source orthographic encoding of the same Quran surface:

- dagger alif is converted to ordinary alif;
- `ىٰ` is treated as long `ā`;
- remaining Uthmani dotless yeh is treated as yeh;
- wasla/ordinary alif differences are normalized;
- hamza-seat differences are ignored for occurrence matching;
- silent final alif after plural wāw may be omitted in the simple-plain source.

This is **not** lexical fuzzy matching.

## Required examples

### 57:3 — ظَاهِر

Retained surface:

```text
الظَّاهِرُ
```

Must resolve to:

```text
qac-form:Zhr:Za`hir:nominal:-
root_id 0480
public form form_zahir_active
Active participle
8 Quran occurrences of the root-dictionary form
```

### 59:23 — سَلَام

Retained surface:

```text
السَّلَامُ
```

Must resolve to the QAC occurrence/form actually expressed there:

```text
qac-form:slm:sala`m:nominal:-
root_id 1351
public form slm-salam
```

It must **not** resolve to:

```text
qac-form:slm:salam:nominal:-
```

That is a different Quran form whose root-dictionary form has 5 occurrences.

## Additional safety rules

- `اللَّه` may only attach to root ID `0110`.
- A public form may only be emitted if one of its `form_group_ids` was actually observed at a retained descriptor occurrence.
- Ambiguous top-scoring QAC surface matches are left unmatched rather than guessed.
- Multiword descriptors remain intentionally outside this one-word morphology enrichment.
- `semantic_exclusions_v1` remains the preferred corpus when present.
- Original Phase-2 and semantic-version files are never modified.

## Output model change

The descriptor JSON now separates:

- `form_resolution_status`
- `matched_occurrence_count`
- `unmatched_occurrence_count`
- `occurrence_link_coverage`
- `observed_form_group_ids`

This prevents an occurrence-link problem from being misreported as “the form cannot be located.”

## Pre-install regression test performed

The v1.4 occurrence-surface resolver was tested against the complete pre-exclusion reviewed Phase-2 corpus and the full QAC form inventory:

```text
one-word descriptor occurrences tested: 4,868
QAC form-group resolutions:            4,868
unresolved QAC form groups:                 0
```

This test validates the occurrence-surface → exact QAC form-group step only. Final public-form resolution still runs against the user's local `final/numbered_roots_v8/` during the normal builder execution.
