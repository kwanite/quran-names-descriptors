# Names of Allah Corpus — Finalization and GitHub Publication Runbook

This bundle starts from the validated semantic-v2 state:

- 225 lexical identities
- 5,037 numbered occurrences
- 404 exact numbered-verse surfaces
- root-form builder 1.4.1
- 125/125 one-word identities matched
- 4,798/4,798 one-word occurrences matched
- 100 multiword identities remaining for deterministic constituent/root linkage

## Licensing model

This project uses the same layered approach as the sibling Quran Roots Dictionary repository:

- project-owned copyrightable material: GPL-3.0-only, to the extent rights are held by the project;
- Tanzil Quran text: CC BY 3.0, verbatim and attributed;
- QAC-derived morphology/root fields: upstream QAC terms apply, with an explicit caveat because QAC's public download page and FAQ are not fully internally consistent about reuse;
- raw Quran Foundation/Quran.com API content: not redistributed;
- local English verse-translation payloads: not redistributed unless separate rights are confirmed.

The public repository does include project-derived descriptor transliterations and concise English descriptor glosses.

## Before finalization

Run `20_patch_descriptor_viewer_semantic_v2.py` if it has not already been run so the private/local review viewer is synchronized with semantic v2. The GitHub Pages viewer generated later is a separate public-safe viewer and does not depend on Quran Foundation or local translation payloads.

## Finalization order

1. `21_build_preferred_quran_surfaces_v1.py`
2. `22_build_multiword_root_links_v1.py`
3. `23_build_basmala_augmentation_v1.py`
4. `24_build_publication_freeze_v1.py`
5. `25_build_github_public_release_v1.py`
6. `26_validate_github_public_release_v1.py`

Do not use `--overwrite` unless intentionally regenerating an already-reviewed deterministic artifact.

## Preferred display surfaces

A public display surface is never synthesized. It must be an exact Quran-attested member surface of the lexical identity.

Selection is deterministic:

1. highest retained numbered-verse occurrence count;
2. earliest Quran occurrence on ties;
3. Unicode order as a final tie-break.

## Multiword root linkage

Multiword descriptors remain semantic wholes. The bridge uses descriptor verse/offset evidence to identify source lexical token positions, then stable `word_order`/`word_location` identifiers from Quran Roots. Text is used only as a post-join validation guard. Root IDs and segment locations are copied from the existing verified word-analysis dataset; QAC form-group IDs are resolved by exact segment location.

If this stage reports `REVIEW REQUIRED`, stop and inspect its `unresolved` array. Do not force or fuzzy-match a root.

## Basmala augmentation

The 112 `ayah:0` opening basmalas are preserved source records, not canonical numbered verses. The augmentation uses only exact full-token surfaces already present in the finalized semantic map and must produce exactly 336 descriptor occurrences (three per basmala). It creates no new lexical identity and fabricates no QAC record.

## Publication freeze

`24_build_publication_freeze_v1.py` embeds machine-readable source/license provenance in the publication JSON files. The final data directory must validate before any public staging occurs.

## GitHub Pages release

`25_build_github_public_release_v1.py` creates a separate public repository tree with:

- the complete publication-final data;
- GPL `LICENSE` copied from the verified sibling Quran Roots repository;
- `LICENSE_SCOPE.md`;
- `THIRD_PARTY_NOTICES.md`;
- `data/DATA_LICENSE.md`;
- `docs/LICENSING.md`;
- `docs/SOURCE_PROVENANCE.md`;
- static `index.html` + `assets/` GitHub Pages viewer;
- `.nojekyll` for straightforward Pages hosting.

The Pages viewer reads only the publication-final JSON under `data/`. It shows all final descriptors, Arabic Quran context, project-derived descriptor gloss/transliteration, counts, and root/form evidence. It does not bundle QF content or local English verse translations.

## Final public validation

Run `26_validate_github_public_release_v1.py` against the staged repository before `git init` or pushing. It verifies counts, license files, Pages assets, public data presence, and absence of known QF/translation payload keys.
