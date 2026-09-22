# License scope

## Project-owned material

Except where a file or directory says otherwise, copyrightable material in
this repository for which the Quranic Names and Descriptors of Allah Project
controls the rights is offered under the **GNU General Public License, version
3 only (GPL-3.0-only)**.

This includes, to the extent rights are held by the project:

- publication/build/validation scripts;
- maintained research pipeline scripts authored for this project;
- the static website / GitHub Pages viewer;
- project documentation;
- the arrangement/compilation of the public release;
- original human-authored and AI-assisted synthesis/editing embodied in the
  descriptor corpus, transliterations, glosses, review decisions, and display
  metadata, to the extent such material is copyrightable and the project has
  rights to license it.

The full GPLv3 text is in `LICENSE`.

## Third-party material is not relicensed

The project cannot grant rights it does not own. Third-party source material,
annotations, databases, editions, trademarks, and other rights remain subject
to their own licenses and terms.

See:

- `THIRD_PARTY_NOTICES.md`
- `data/DATA_LICENSE.md`
- `docs/LICENSING.md`
- `docs/SOURCE_PROVENANCE.md`

## Important QAC limitation

The public corpus is materially informed by Quranic Arabic Corpus (QAC)
morphology and annotations. QAC's current public pages are not fully internally
consistent about reuse:

- the download page identifies the morphology data as GNU GPL and links GPLv3;
- the download terms also state that verbatim copies of the morphology file
  may not be changed and require QAC attribution in derived works;
- the QAC FAQ separately describes research use as non-commercial.

Because this project cannot resolve that inconsistency on QAC's behalf, this
repository does **not** represent that the QAC-derived parts of `data/` are
cleared for unrestricted commercial use.

Until QAC provides clarification or separate permission, downstream users
should treat the QAC-derived dataset as suitable for research/non-commercial
reuse under the applicable QAC terms, or obtain permission from QAC for a use
that depends on broader rights.

This QAC caveat does not restrict independently authored project code that
does not contain QAC data.

## Quran Foundation boundary

Raw Quran Foundation/Quran.com API content is not included in this public
repository. The public viewer is generated from the publication-final corpus
and does not bundle QF word-by-word content, QF transliteration payloads,
translations, raw API responses, or other QF Content.

Project-derived transliterations and concise English descriptor glosses are
separate project metadata and are included to the extent the project controls
rights in them.

Quran Foundation's current Developer Terms prohibit redistribution of QF
Content or raw API data without a separate written license. This repository
therefore does not grant or purport to grant redistribution rights in QF
Content.

## No warranty / no legal advice

GPLv3's warranty disclaimer applies to GPL-covered project material.

The licensing notes in this repository document the project's best-effort
reading of the cited upstream materials as of 2026-09-22. They are not legal
advice and do not replace the upstream terms.

