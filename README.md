# Names & Descriptors of Allah in the Quran

**A Quran-only, text-first research corpus. This is not a traditional “Names of Allah” list.**

**Interactive viewer:** https://kwanite.github.io/quran-names-descriptors/

**Method:** [docs/METHOD.md](docs/METHOD.md)

This project asks a different question:

> **What names and explicit descriptive expressions does the Quran itself use for Allah when the Quran is examined without beginning from a pre-existing list of divine names?**

The extraction was deliberately Quran-first. A classical or traditional list of the 99 Names was **not** supplied as a seed, checklist, or authority for deciding what should appear. Each retained expression had to be supported by its Quranic occurrence and context.

## Why “descriptors”?

The word **descriptors** is deliberate. The Quran refers to and describes Allah not only with conventional name-like expressions, but also with explicit nouns, adjectives, participles, and multiword nominal/adjectival expressions.

This corpus records that broader Quranic evidence without automatically declaring every retained expression to be a formal theological “Name of Allah.” Doing otherwise would impose a later classification on the Quranic evidence that this project was specifically designed not to assume.

Finite verbs are not converted into inferred divine descriptors merely because they describe something Allah does. The corpus focuses on explicit referential/descriptive language actually used of Allah in context.

## Browse the data

The GitHub Pages viewer is the easiest way to browse the corpus in a user-friendly form: https://kwanite.github.io/quran-names-descriptors/

The viewer exposes:

- the Quran-attested Arabic display form;
- transliteration;
- the project’s concise English meaning/gloss for every descriptor;
- exact retained Quranic surface forms;
- all retained occurrences;
- direct links to the Quran reader;
- exact one-word morphology/root evidence;
- direct links to the full Quran Roots Dictionary;
- constituent-root evidence for multiword descriptors.

The viewer is static and reads only publication-final files in `data/`. It does **not** bundle Quran Foundation/Quran.com API payloads or private/local full-verse English translation files.

## Publication v1

- 225 reviewed lexical identities
- 5,037 retained numbered-verse descriptor occurrences
- 404 retained exact numbered-verse surfaces
- 112 preserved unnumbered opening basmalas (`ayah:0`)
- 336 deterministic descriptor occurrences from those basmalas
- 5,373 combined Quran-text descriptor occurrences
- exact one-word root/form links for 4,798 numbered occurrences
- deterministic constituent/root links for 239 multiword numbered occurrences

See `data/validation_report.json` and `data/manifest.json` for machine-readable release assertions and checksums.

For the research design, extraction rules, semantic review, root-linking method, basmala handling, and publication validation, see **[docs/METHOD.md](docs/METHOD.md)**.

## Data model

The project deliberately separates:

`exact Quran occurrence → exact Quran surface → reviewed lexical identity → preferred Quran-attested display surface`

A preferred display surface is always selected from forms actually attested in the Quran. No unattested Arabic display form is synthesized.

Multiword descriptors remain semantic wholes even when their constituent Quran words link to multiple roots.

## Repository layout

- `index.html`, `assets/` — static GitHub Pages viewer
- `data/` — publication-final corpus and validation artifacts
- `scripts/` — publication/reproducibility scripts
- `docs/METHOD.md` — research method and pipeline
- `docs/` — provenance, licensing, and release documentation
- `LICENSE` — GPL-3.0-only text for project-owned material
- `LICENSE_SCOPE.md` — explains the boundary between project-owned and third-party material
- `THIRD_PARTY_NOTICES.md` — upstream source/license notices

## Licensing

Project-owned copyrightable material is offered under **GPL-3.0-only** to the extent the project controls those rights. Third-party Quran text and annotations are not relicensed. See `LICENSE_SCOPE.md`, `data/DATA_LICENSE.md`, `docs/LICENSING.md`, `docs/SOURCE_PROVENANCE.md`, and `THIRD_PARTY_NOTICES.md`.

## Public-release boundary

The release includes the full reviewed descriptor corpus, Quran-attested Arabic surfaces and verse context, project-derived transliterations/glosses, exclusion history, and root-link data. It intentionally excludes raw Quran Foundation/Quran.com API content and local full-verse English translation payloads unless separate redistribution rights are established.
