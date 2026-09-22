# Names of Allah Corpus — Semantic Exclusions v1

**Date:** 2026-09-13  
**Status:** ACCEPTED EXCLUSION SET / derived corpus version  
**Source corpus:** `runs/phase1_full_v3_2_1/phase2_global_audit_sol_v3/`  
**Output corpus:** `runs/phase1_full_v3_2_1/semantic_exclusions_v1/`

## Decision

This version preserves the Phase-2 reviewed source files unchanged and creates a new derived corpus by excluding 22 lexical identities accepted by the user during semantic review.

The operation is identity-level: every occurrence and exact surface assigned to an excluded lexical identity is removed from the derived corpus. The original Phase-2 data and the complete exclusion ledger are retained for auditability.

## Count effect

| Measure | Source Phase 2 | Excluded | Semantic v1 retained |
|---|---:|---:|---:|
| Lexical identities | 255 | 22 | 233 |
| Descriptor occurrences | 5,117 | 50 | 5,067 |
| Exact Quran surfaces | 446 | 31 | 415 |

## Exclusions

### Negative / denied / non-divine attribution

| ID | Arabic | Transliteration | Meaning | Occ. | Quran locations | Rationale |
|---|---|---|---|---:|---|---|
| SEMEX-V1-001 | غَافِل | Ghāfil | Heedless / unaware | 11 | 2:74, 2:85, 2:140, 2:144, 2:149, 3:99, 6:132, 11:123, 14:42, 23:17, 27:93 | Negative sentence: the Quran denies heedlessness/unawareness of God. |
| SEMEX-V1-002 | ظَلَّام | Ẓallām | Very unjust / wronging | 5 | 3:182, 8:51, 22:10, 41:46, 50:29 | Negative sentence: the Quran denies that God is extremely unjust / wronging. |
| SEMEX-V1-003 | مَسْبُوق | Masbūq | Outstripped / forestalled | 2 | 56:60, 70:41 | Negative sentence: the Quran denies that God can be outstripped / forestalled. |
| SEMEX-V1-004 | إِلَـٰه غَيْر | Ilāh ghayr | Another / other deity | 1 | 26:29 | Pharaoh's words about taking another deity; not a Quran-endorsed descriptor of the one God. |
| SEMEX-V1-005 | ظَالِم | Ẓālim | Unjust / wrongdoer | 1 | 26:209 | Negative sentence: the Quran denies wrongdoing / injustice of God. |
| SEMEX-V1-006 | غَائِب | Ghāʾib | Absent | 1 | 7:7 | Negative sentence: the Quran denies absence. |
| SEMEX-V1-007 | فَقِير | Faqīr | Poor / needy | 1 | 3:181 | False hostile attribution reported from others: they say that God is poor/needy. |
| SEMEX-V1-008 | لَاعِب | Lāʿib | Playing / player | 1 | 44:38 | Negative sentence: the Quran denies that God's creation is play. |
| SEMEX-V1-009 | نَسِيّ | Nasiyy | Forgetful | 1 | 19:64 | Negative sentence: 'your Lord is not forgetful'; the denied predicate must not become a descriptor. |

### Body-part language

| ID | Arabic | Transliteration | Meaning | Occ. | Quran locations | Rationale |
|---|---|---|---|---:|---|---|
| SEMEX-V1-010 | يَد | Yad | Hand | 3 | 36:71, 36:83, 38:75 | Human body-part term used rhetorically/analogically; excluded as a standalone definition of God. |
| SEMEX-V1-011 | عَيْن | ʿAyn | Eye | 2 | 20:39, 54:14 | Human body-part term used rhetorically/analogically; excluded as a standalone definition of God. |
| SEMEX-V1-012 | وَجْه | Wajh | Face | 2 | 6:52, 28:88 | Human body-part term used rhetorically/analogically; excluded as a standalone definition of God. |

### Too specific / contextual

| ID | Arabic | Transliteration | Meaning | Occ. | Quran locations | Rationale |
|---|---|---|---|---:|---|---|
| SEMEX-V1-013 | إِلَـٰه مُوسَىٰ | Ilāh Mūsā | God of Moses | 2 | 28:38, 40:37 | Pharaoh-context expression 'God of Moses'; too speaker-/context-specific for the descriptor inventory. |
| SEMEX-V1-014 | رَبّ مُوسَىٰ وَهَارُون | Rabb Mūsā wa-Hārūn | Lord of Moses and Aaron | 2 | 7:122, 26:48 | Believers' expression 'Lord of Moses and Aaron'; valid in context but too specific for the retained descriptor inventory. |
| SEMEX-V1-015 | رَبّ هَارُون وَمُوسَىٰ | Rabb Hārūn wa-Mūsā | Lord of Aaron and Moses | 1 | 20:70 | Context-specific contrast identifying the one true God worshipped by Aaron and Moses; too specific for the retained descriptor inventory. |

### Too general

| ID | Arabic | Transliteration | Meaning | Occ. | Quran locations | Rationale |
|---|---|---|---|---:|---|---|
| SEMEX-V1-016 | جَاعِل | Jāʿil | Maker / one who makes | 3 | 2:30, 3:55, 28:7 | Too general as a standalone identity ('maker/one who makes'); excluded from the curated descriptor set. |
| SEMEX-V1-017 | فَاعِل | Fāʿil | Doer | 3 | 21:17, 21:79, 21:104 | Too general as a standalone identity ('doer'); excluded from the curated descriptor set. |
| SEMEX-V1-018 | فَعَّال | Faʿʿāl | Effecter / doer | 2 | 11:107, 85:16 | Too general as a standalone identity ('effecter/doer'); excluded from the curated descriptor set. |

### Other scope exclusions

| ID | Arabic | Transliteration | Meaning | Occ. | Quran locations | Rationale |
|---|---|---|---|---:|---|---|
| SEMEX-V1-019 | عِزَّة | ʿIzza | Might / honor | 2 | 38:82, 63:8 | Abstract noun 'might/honor', not an explicit standalone descriptor; the related descriptor ʿAzīz already covers the concept. |
| SEMEX-V1-020 | نَفْس | Nafs | Self | 2 | 6:54, 20:41 | Functions as self-reference ('Himself/Myself') rather than as an independent descriptor. |

### Relational ordinal numbers

| ID | Arabic | Transliteration | Meaning | Occ. | Quran locations | Rationale |
|---|---|---|---|---:|---|---|
| SEMEX-V1-021 | رَابِع | Rābiʿ | Fourth | 1 | 58:7 | Relational ordinal in a passage about God's presence with a group; not a rank or standalone divine descriptor. |
| SEMEX-V1-022 | سَادِس | Sādis | Sixth | 1 | 58:7 | Relational ordinal in a passage about God's presence with a group; not a rank or standalone divine descriptor. |

## Files

- `semantic_exclusions_manifest.json` — authoritative exclusion decision record.
- `excluded_descriptors.json` / `.csv` — descriptor-level exclusion list.
- `excluded_occurrences.json` — all 50 removed occurrence records with decision IDs.
- `surface_to_lexeme_map_reviewed.json` — filtered 415-surface map.
- `lexical_groups_reviewed.json` — filtered 233 identity groups.
- `descriptor_occurrences_lexical.json` — filtered 5,067-occurrence ledger.
- `lexical_frequency.json` — recomputed 233-identity frequencies.

## Preservation rule

Do not delete or overwrite `phase2_global_audit_sol_v3`. It remains the historical reviewed Phase-2 source. `semantic_exclusions_v1` is a new derived semantic version.

Future semantic exclusions or restorations should create `semantic_exclusions_v2` (or a later semantic version), not silently rewrite this decision record.

## Viewer

The viewer patch changes only the viewer corpus paths and visible version label so it reads `semantic_exclusions_v1`. It does not rewrite the original Phase-2 data.

### Root-form enrichment safety

The viewer patch checks any existing `descriptor_root_forms.json`. If it is not builder version 1.2 or if the `اللَّه` sanity check fails, the old root-form enrichment files are moved into `archive/root_form_enrichment/` rather than displayed. This prevents the known v1.1 positional-join bug from contaminating semantic-v1 inspection.
