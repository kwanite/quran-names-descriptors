#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

PUBLIC_DATA_FILES = [
    "descriptors.json",
    "occurrence_ledger.json",
    "lexical_index.json",
    "exclusion_history.json",
    "root_links.json",
    "manifest.json",
    "validation_report.json",
    "SHA256SUMS",
]

README = r"""# Names & Descriptors of Allah in the Quran

**A Quran-only, text-first research corpus. This is not a traditional “99 Names of Allah” list.**

This project asks a different question:

> **What names and explicit descriptive expressions does the Quran itself use for Allah when the Quran is examined without beginning from a pre-existing list of divine names?**

The extraction was deliberately Quran-first. A classical or traditional list of the 99 Names was **not** supplied as a seed, checklist, or authority for deciding what should appear. Each retained expression had to be supported by its Quranic occurrence and context.

## Why “descriptors”?

The word **descriptors** is deliberate. The Quran refers to and describes Allah not only with conventional name-like expressions, but also with explicit nouns, adjectives, participles, and multiword nominal/adjectival expressions.

This corpus records that broader Quranic evidence without automatically declaring every retained expression to be a formal theological “Name of Allah.” Doing otherwise would impose a later classification on the Quranic evidence that this project was specifically designed not to assume.

Finite verbs are not converted into inferred divine descriptors merely because they describe something Allah does. The corpus focuses on explicit referential/descriptive language actually used of Allah in context.

## Browse the data

The GitHub Pages viewer is the easiest way to browse the corpus in a user-friendly form. After Pages is enabled for this repository, the site is served directly from the repository root.

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

## Data model

The project deliberately separates:

`exact Quran occurrence → exact Quran surface → reviewed lexical identity → preferred Quran-attested display surface`

A preferred display surface is always selected from forms actually attested in the Quran. No unattested Arabic display form is synthesized.

Multiword descriptors remain semantic wholes even when their constituent Quran words link to multiple roots.

## Repository layout

- `index.html`, `assets/` — static GitHub Pages viewer
- `data/` — publication-final corpus and validation artifacts
- `scripts/` — publication/reproducibility scripts
- `docs/` — method, provenance, licensing, and release documentation
- `LICENSE` — GPL-3.0-only text for project-owned material
- `LICENSE_SCOPE.md` — explains the boundary between project-owned and third-party material
- `THIRD_PARTY_NOTICES.md` — upstream source/license notices

## Licensing

Project-owned copyrightable material is offered under **GPL-3.0-only** to the extent the project controls those rights. Third-party Quran text and annotations are not relicensed. See `LICENSE_SCOPE.md`, `data/DATA_LICENSE.md`, `docs/LICENSING.md`, `docs/SOURCE_PROVENANCE.md`, and `THIRD_PARTY_NOTICES.md`.

## Public-release boundary

The release includes the full reviewed descriptor corpus, Quran-attested Arabic surfaces and verse context, project-derived transliterations/glosses, exclusion history, and root-link data. It intentionally excludes raw Quran Foundation/Quran.com API content and local full-verse English translation payloads unless separate redistribution rights are established.
"""

LICENSE_SCOPE = r"""# License scope

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
"""

THIRD_PARTY = r"""# Third-Party Notices

## Tanzil Quran Text

Arabic Quran text in this release derives from the Tanzil Quran Text.

Tanzil Quran Text  
Copyright (C) 2007-2021 Tanzil Project  
License: Creative Commons Attribution 3.0

Tanzil permits copying and distributing verbatim copies of its Quran text,
prohibits changing the text, requires clear source attribution and a link to
Tanzil, and requires the notice to be reproduced appropriately in files
derived from or containing a substantial portion of the text.

- Terms: https://tanzil.net/docs/Text_License
- Project: https://tanzil.net/

The publication corpus preserves Quran text verbatim from the project's frozen
source and identifies Tanzil in the machine-readable provenance blocks.

## Quranic Arabic Corpus

Morphology, root identities, word/segment locations, and QAC form-group
identifiers derive from the Quranic Arabic Corpus (version 0.4), by Kais
Dukes.

QAC's download page labels the morphology data GNU GPL and imposes attribution
and verbatim-copy conditions. Its FAQ separately describes the research data
as non-commercial. Because those public statements are not fully internally
consistent, this repository carries the QAC caveat described in
`LICENSE_SCOPE.md` and `data/DATA_LICENSE.md`.

- Download/terms: https://corpus.quran.com/download/
- GPL page: https://corpus.quran.com/license.jsp
- FAQ: https://corpus.quran.com/faq.jsp

## Quran Foundation / Quran.com

Raw Quran Foundation/Quran.com API content is not redistributed in this public
repository. In particular, the public release does not bundle QF word-by-word
payloads, QF transliteration payloads, translations, or raw API responses.

Current terms: https://api-docs.quran.foundation/legal/developer-terms/

## English translations

English verse-translation files used in private/local review tooling are not
copied into this public repository. The public viewer displays the Arabic
Quran context plus project-derived descriptor glosses. Translation text may be
added later only after redistribution rights for the selected edition are
confirmed.
"""

DATA_LICENSE = r"""# Data license and source boundaries

The public `data/` directory is a compilation containing several rights layers.

## Project-owned layer

To the extent the project owns copyright in the selection, arrangement,
review decisions, lexical identities, project-derived transliterations,
concise English descriptor glosses, validation metadata, and other original
synthesis, that project-owned material is offered under **GPL-3.0-only**.

## Tanzil Quran text

Arabic Quran text and exact Quran-attested strings derive from Tanzil Quran
Text and remain subject to Tanzil's **CC BY 3.0** terms, including the
requirement that the Quran text remain verbatim and that Tanzil be attributed.

https://tanzil.net/docs/Text_License

## Quranic Arabic Corpus-derived fields

Root IDs, word/segment locations, morphology, and identifiers are
materially informed by QAC. QAC's download page states GNU GPL while its FAQ
also describes research/non-commercial use. This repository does not resolve
that inconsistency or represent the QAC-derived layer as cleared for
unrestricted commercial reuse.

https://corpus.quran.com/download/
https://corpus.quran.com/faq.jsp

## Quran Foundation boundary

No raw Quran Foundation/Quran.com API content is included in `data/`.
Project-derived transliterations/glosses are included as project metadata, not
as copied QF API payloads.

## Practical reading

The repository-level GPL applies only to rights the project can license. It
does not erase or replace the separate upstream terms that attach to Tanzil
and QAC-derived material.
"""

LICENSING = r"""# Licensing notes

This repository follows the same layered licensing approach used by the Quran
Roots Dictionary Project.

1. Project-owned code, viewer, documentation, compilation/arrangement, and
   original synthesis are offered under GPL-3.0-only to the extent rights are
   held by the project.
2. Tanzil Quran text remains under CC BY 3.0 and must remain verbatim with
   attribution.
3. QAC-derived morphology/root data remains subject to QAC's upstream terms.
   QAC's public download and FAQ pages are not fully internally consistent, so
   the project carries an explicit research/non-commercial caveat for QAC-
   derived data rather than overstating downstream rights.
4. Raw Quran Foundation/Quran.com API content is not redistributed.
5. Private/local English verse-translation payloads are not redistributed
   until the relevant edition's redistribution rights are separately confirmed.

These notes are a best-effort source-boundary record, not legal advice.
"""

SOURCE_PROVENANCE = r"""# Source provenance

## Immutable Quran source

The research pipeline uses `quran-simple-plain.json` as its frozen Quran text
source.

SHA-256:

`10b63cb29e329de93f80ff60eb332e52b3a72be8f68f6eb6272a03d4cb16084c`

The source contains 114 surahs, 6,236 numbered ayahs, and 112 preserved
unnumbered opening basmalas represented as `ayah:0` records.

Arabic Quran text derives from Tanzil Quran Text.

## Semantic pipeline

- Phase 1: exact Quran surface extraction + referent/context check
- Phase 2: lexical normalization/reconciliation
- semantic review checkpoint: `semantic_exclusions_v2`
- final preferred surface: exact Quran-attested form only
- numbered root/form linkage: Quran Roots/QAC stable occurrence identifiers
- ayah:0 augmentation: deterministic exact-surface matching after semantic freeze

## Final publication counts

- 225 lexical identities
- 5,037 numbered occurrences
- 404 exact numbered-verse surfaces
- 125 one-word identities / 4,798 one-word numbered occurrences
- 100 multiword identities / 239 multiword numbered occurrences
- 112 unnumbered basmalas
- 336 basmala descriptor occurrences
- 5,373 combined descriptor occurrences

## Quranic Arabic Corpus

QAC supplies morphology/root evidence used through the sibling Quran Roots
data pipeline. No root is inferred from spelling.

## Quran Foundation / English translations

The private review viewer may use additional contextual display resources.
Those payloads are not copied into the public dataset or the public Pages
viewer. The public viewer is built solely from publication-final files in
`data/`.
"""

PUBLIC_BOUNDARY = r"""# Public release boundary

The public repository includes all publication-final semantic corpus data,
exact Arabic occurrence evidence, exclusion history, preferred display forms,
root-link data, validation artifacts, scripts, documentation, and a static
GitHub Pages viewer.

It deliberately excludes:

- private run directories and intermediate API responses;
- archives/backups;
- credentials and environment files;
- raw Quran Foundation/Quran.com API content;
- local English verse-translation files whose redistribution rights have not
  been separately established.

Those exclusions are licensing/provenance boundaries, not omissions from the
final reviewed semantic corpus.
"""

GITIGNORE = r""".DS_Store
__pycache__/
*.pyc
.venv/
venv/
.env
.env.*
archive/
runs/
raw/
*.zip
"""

INDEX_HTML = r'''<!doctype html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="A Quran-only, text-first corpus of names and explicit descriptors used for Allah in the Quran, built without using the traditional 99 Names as a seed.">
  <title>Names & Descriptors of Allah in the Quran — Quran-only corpus</title>
  <link rel="stylesheet" href="./assets/styles.css">
</head>
<body>
  <div id="loading" class="loading">
    <strong>Loading publication corpus…</strong>
    <div class="small">225 reviewed lexical identities · publication v1</div>
  </div>

  <div id="app" class="app" hidden>
    <aside id="sidebar" class="sidebar">
      <div class="sidebar-head">
        <div class="eyebrow">Quran-only · text-first corpus</div>
        <h1>Names &amp; Descriptors of Allah in the Quran</h1>
        <div class="small">225 reviewed identities · 5,373 combined occurrences</div>
        <button id="closeSidebar" class="btn mobile-only sidebar-close" type="button">Close</button>
      </div>

      <div class="sidebar-controls">
        <label class="control-label" for="search">Search</label>
        <input id="search" class="search" type="search"
          placeholder="Try rahman, rahim, alim, Arabic, or an English meaning…" autocomplete="off">

        <label class="control-label" for="typeFilter">Type</label>
        <select id="typeFilter" class="select">
          <option value="all">All descriptors</option>
          <option value="one">One-word only</option>
          <option value="multi">Multiword only</option>
        </select>
      </div>

      <div class="list-meta">
        <span>Publication v1</span>
        <span id="listCount">225</span>
      </div>

      <nav id="descriptorList" class="descriptor-list" aria-label="Descriptors"></nav>

    </aside>

    <main class="main">
      <div class="mobile-bar">
        <button id="openSidebar" class="btn mobile-only" type="button">Browse descriptors</button>
        <div class="mobile-brand">Names &amp; Descriptors in the Quran</div>
      </div>

      <div id="detail" class="detail">
        <div class="empty-state">Select a descriptor to inspect its Quran evidence.</div>
      </div>
    </main>
  </div>

  <script src="./assets/app.js" defer></script>
</body>
</html>
'''

STYLES = r''':root {
  color-scheme: dark;
  --bg: #0b0d10;
  --sidebar-bg: #0d1014;
  --panel: #11151a;
  --panel2: #161b22;
  --panel3: #1c232c;
  --text: #f2f1ec;
  --muted: #9aa4b2;
  --dim: #6f7c89;
  --line: #27313d;
  --accent: #d8bd78;
  --accent2: #8fb7a5;
  --mark: #574b26;
  --sidebar: 360px;
  --radius: 14px;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  min-height: 100%;
  background: var(--bg);
  color: var(--text);
}

body {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.45;
}

button, input, select { font: inherit; }
button { cursor: pointer; }
a { color: #b9d9cb; }
a:hover { color: #d5e9e0; }

.app {
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--sidebar) minmax(0, 1fr);
}

.loading, .fatal {
  max-width: 760px;
  margin: 80px auto;
  padding: 24px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.small { color: var(--muted); font-size: 12px; }

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--line);
}

.sidebar-head {
  position: relative;
  padding: 22px 20px 17px;
  border-bottom: 1px solid var(--line);
}

.eyebrow {
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: .12em;
  font-size: 11px;
  font-weight: 700;
}

.sidebar h1 {
  margin: 5px 0 6px;
  font-size: 20px;
  line-height: 1.2;
  max-width: 280px;
}

.sidebar-controls {
  padding: 14px 14px 11px;
  border-bottom: 1px solid #171d24;
}

.control-label {
  display: block;
  margin: 0 2px 5px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .08em;
  font-size: 10px;
}

.control-label:not(:first-child) { margin-top: 11px; }

.search, .select {
  width: 100%;
  border: 1px solid var(--line);
  background-color: var(--panel);
  color: var(--text);
  padding: 10px 11px;
  border-radius: 9px;
  outline: none;
}

.search:focus, .select:focus {
  border-color: #596879;
  box-shadow: 0 0 0 3px #1c2630;
}

.select {
  appearance: none;
  -webkit-appearance: none;
  padding-right: 46px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='9' viewBox='0 0 14 9'%3E%3Cpath d='M1 1.5 7 7.5 13 1.5' fill='none' stroke='%23d8dee6' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 16px center;
  background-size: 14px 9px;
}

.list-meta {
  padding: 10px 16px 7px;
  color: var(--muted);
  font-size: 11px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.descriptor-list {
  overflow: auto;
  padding: 0 8px 16px;
  flex: 1 1 auto;
}

.descriptor-item {
  width: 100%;
  min-width: 0;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  padding: 10px 10px;
  border-radius: 11px;
  margin: 2px 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 9px;
}

.descriptor-item:hover { background: var(--panel); }
.descriptor-item.active {
  background: var(--panel2);
  border-color: #3b4654;
}

.descriptor-copy { min-width: 0; }

.descriptor-ar {
  display: block;
  direction: rtl;
  text-align: left;
  font-family: "Noto Naskh Arabic", "Amiri", "Noto Sans Arabic", serif;
  font-size: 22px;
  line-height: 1.35;
  white-space: normal;
  overflow-wrap: anywhere;
}

.descriptor-tr {
  color: var(--accent2);
  font-size: 12px;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.descriptor-meaning {
  color: var(--muted);
  font-size: 11px;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count-pill {
  align-self: center;
  min-width: 42px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  background: #0b0e12;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px 7px;
  font-size: 10px;
}


.main {
  min-width: 0;
  padding: 28px 34px 72px;
}

.detail {
  width: min(1180px, 100%);
  margin: 0 auto;
  min-width: 0;
}

.mobile-bar { display: none; }

.utility-row {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 14px;
}

.utility-row a { text-decoration: none; }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #3a4653;
  background: var(--panel2);
  color: var(--text);
  border-radius: 9px;
  padding: 7px 10px;
  font-size: 12px;
  text-decoration: none;
}

.btn:hover { background: #202935; }
.btn.primary {
  border-color: #6d623d;
  color: #f0dca7;
  background: #1c1911;
}

.descriptor-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 6px;
  padding: 6px 0 2px;
  min-width: 0;
}

.title-ar {
  direction: rtl;
  unicode-bidi: plaintext;
  text-align: left;
  display: block;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  margin: 0;
  font-family: "Noto Naskh Arabic", "Amiri", "Noto Sans Arabic", serif;
  font-size: clamp(36px, 5.4vw, 62px);
  line-height: 1.32;
  font-weight: 500;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: normal;
}

.title-tr {
  color: var(--accent2);
  font-size: clamp(17px, 2vw, 21px);
  overflow-wrap: anywhere;
}

.title-meaning {
  max-width: 820px;
  color: var(--muted);
  font-size: 15px;
  margin-top: 1px;
}

.title-meaning-label {
  display: inline-block;
  margin-right: 7px;
  color: var(--accent);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .08em;
  text-transform: uppercase;
}


.descriptor-root-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
}

.descriptor-root-card {
  border: 1px solid #354338;
  border-radius: 11px;
  background: #0d1310;
  padding: 14px;
}

.descriptor-root-head {
  display: flex;
  gap: 12px;
  align-items: baseline;
  flex-wrap: wrap;
}

.descriptor-root-arabic {
  direction: rtl;
  font-family: "Noto Naskh Arabic", "Amiri", serif;
  color: #f0ead8;
  font-size: 24px;
}

.descriptor-root-meta {
  margin-top: 7px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.root-dictionary-link {
  display: inline-flex;
  margin-top: 11px;
  text-decoration: none;
}

.root-inline-link {
  color: #ead69f;
  text-decoration: underline;
  text-decoration-color: #6d623d;
  text-underline-offset: 3px;
}

.root-inline-link:hover {
  color: #fff0bd;
}

.stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 20px 0 22px;
}

.stat {
  min-width: 0;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 13px 14px;
}

.stat .k {
  font-size: 10px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .08em;
}

.stat .v {
  margin-top: 4px;
  font-size: 19px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  margin-top: 14px;
  overflow: hidden;
}

.section-head {
  padding: 13px 16px;
  display: flex;
  gap: 14px;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--line);
}

.section h2 {
  font-size: 14px;
  margin: 0;
}

.section-sub {
  color: var(--muted);
  font-size: 11px;
}

.section-body { padding: 16px; }

.surface-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.surface {
  direction: rtl;
  font-family: "Noto Naskh Arabic", "Amiri", "Noto Sans Arabic", serif;
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 18px;
  line-height: 1.45;
}

.occ-list {
  display: grid;
  gap: 9px;
}

.occ {
  border: 1px solid var(--line);
  border-radius: 11px;
  overflow: hidden;
  background: #0f1318;
}

.occ-head {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
}

.verse-key {
  font-weight: 700;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.surface-hit {
  direction: rtl;
  unicode-bidi: plaintext;
  text-align: left;
  font-family: "Noto Naskh Arabic", "Amiri", "Noto Sans Arabic", serif;
  font-size: 19px;
  line-height: 1.45;
  min-width: 0;
  overflow-wrap: anywhere;
}

.occ-id {
  color: var(--dim);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  overflow-wrap: anywhere;
}

.verse-panel {
  border-top: 1px solid var(--line);
  background: #0b0e12;
  padding: 15px 16px 16px;
}

.verse-ar {
  direction: rtl;
  unicode-bidi: plaintext;
  text-align: right;
  font-family: "Noto Naskh Arabic", "Amiri", "Noto Sans Arabic", serif;
  font-size: clamp(23px, 2.4vw, 29px);
  line-height: 1.95;
  color: #faf7ec;
}

.verse-ar mark {
  background: var(--mark);
  color: #fff5cf;
  border-radius: 5px;
  padding: 0 2px;
}

.root-evidence {
  margin-top: 12px;
  color: #c8d0d8;
  font-size: 12px;
  line-height: 1.65;
  padding-top: 10px;
  border-top: 1px dashed #26303a;
}

.morphology-title {
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-size: 10px;
  font-weight: 700;
  margin-bottom: 6px;
}

.morphology-line { margin-top: 4px; }
.morphology-key { color: var(--muted); }
.morphology-value { color: #e8ecef; }

.technical-details {
  margin-top: 9px;
  color: var(--dim);
}

.technical-details summary {
  cursor: pointer;
  color: #8593a2;
  user-select: none;
  width: fit-content;
}

.technical-code {
  margin-top: 7px;
  padding: 8px 10px;
  border: 1px solid #202a34;
  border-radius: 8px;
  background: #090c10;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.translation-note {
  margin-top: 13px;
  padding: 10px 12px;
  border: 1px solid #27313d;
  border-radius: 9px;
  background: #10151a;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}

.translation-note strong {
  color: #d9dee4;
  font-weight: 650;
}

.surface-explainer {
  margin-top: 10px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
  max-width: 820px;
}

.root-label {
  color: var(--accent);
  font-weight: 650;
}

.root-word {
  color: #e9e3d2;
  font-family: "Noto Naskh Arabic", "Amiri", serif;
  font-size: 16px;
}

.more-row {
  display: flex;
  justify-content: center;
  padding-top: 14px;
}

.empty-state {
  color: var(--muted);
  padding: 70px 20px;
  text-align: center;
}

.mobile-only { display: none; }

@media (max-width: 1050px) {
  :root { --sidebar: 320px; }
  .main { padding: 24px 22px 60px; }
  .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .app { display: block; }

  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: min(88vw, 350px);
    z-index: 40;
    transform: translateX(-102%);
    transition: transform .2s ease;
    box-shadow: 14px 0 40px #000a;
  }

  .sidebar.open { transform: translateX(0); }

  .sidebar-close {
    position: absolute;
    right: 14px;
    top: 14px;
  }

  .main { padding: 14px 14px 50px; }

  .mobile-only { display: inline-flex; }

  .mobile-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
  }

  .mobile-brand {
    color: var(--muted);
    font-size: 12px;
    text-align: right;
  }

  .utility-row {
    justify-content: flex-start;
    overflow-x: auto;
  }

  .title-ar {
    font-size: clamp(34px, 12vw, 50px);
    line-height: 1.38;
  }

  .stats {
    grid-template-columns: 1fr 1fr;
  }

  .occ-head {
    grid-template-columns: 76px minmax(0, 1fr);
  }

  .occ-id {
    grid-column: 2 / 3;
  }
}

@media (max-width: 430px) {
  .stats { grid-template-columns: 1fr 1fr; }
  .stat { padding: 11px 12px; }
  .title-ar { font-size: 36px; }
}
'''

APP_JS = r'''(() => {
  const PAGE_SIZE = 40;

  const state = {
    descriptors: [],
    occurrenceByIdentity: new Map(),
    rootByOccurrence: new Map(),
    selected: null,
    visibleOccurrences: PAGE_SIZE,
  };

  const $ = (id) => document.getElementById(id);

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[c]));

  function foldSearch(s) {
    let x = String(s ?? "").toLowerCase();

    const translitMap = {
      "ʿ": "", "ʾ": "", "‘": "", "’": "", "ʻ": "", "ʼ": "", "`": "", "'": "",
      "ħ": "h", "ḫ": "kh", "ġ": "gh", "š": "sh", "č": "ch", "ǧ": "j",
      "ṯ": "th", "ḏ": "dh"
    };
    x = Array.from(x).map(ch => translitMap[ch] ?? ch).join("");
    x = x.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");

    x = x
      .replace(/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]/g, "")
      .replace(/[أإآٱ]/g, "ا")
      .replace(/ى/g, "ي")
      .replace(/ؤ/g, "و")
      .replace(/ئ/g, "ي")
      .replace(/ة/g, "ه")
      .replace(/ـ/g, "")
      .replace(/[^a-z0-9\u0600-\u06ff]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    return x;
  }

  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;

    const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
    const cur = new Array(b.length + 1);

    for (let i = 1; i <= a.length; i++) {
      cur[0] = i;
      for (let j = 1; j <= b.length; j++) {
        cur[j] = Math.min(
          cur[j - 1] + 1,
          prev[j] + 1,
          prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
        );
      }
      for (let j = 0; j <= b.length; j++) prev[j] = cur[j];
    }

    return prev[b.length];
  }

  function similarity(a, b) {
    const maxLen = Math.max(a.length, b.length);
    if (!maxLen) return 1;
    return 1 - levenshtein(a, b) / maxLen;
  }

  function searchScore(query, d) {
    if (!query) return 1;

    const fields = [
      d.lexical_identity_arabic,
      d.preferred_quran_surface,
      d.transliteration,
      d.english_gloss,
      ...(d.numbered_member_surfaces || []),
    ].map(foldSearch).filter(Boolean);

    let best = -1;

    for (const field of fields) {
      if (field === query) best = Math.max(best, 120);
      if (field.startsWith(query)) best = Math.max(best, 110);
      if (field.includes(query)) best = Math.max(best, 100);

      const compact = field.replace(/\s+/g, "");
      const qCompact = query.replace(/\s+/g, "");
      if (compact.includes(qCompact)) best = Math.max(best, 95);

      for (const token of field.split(" ")) {
        if (token.startsWith(query)) best = Math.max(best, 90);
        if (query.length >= 3 && token.length >= 3) {
          const sim = similarity(query, token);
          if (sim >= 0.67) best = Math.max(best, 55 + sim * 30);
        }
      }

      if (query.length >= 4 && field.length <= 40) {
        const sim = similarity(query, field);
        if (sim >= 0.72) best = Math.max(best, 50 + sim * 25);
      }
    }

    return best;
  }

  function isMulti(d) {
    return String(d.lexical_identity_arabic || "").trim().split(/\s+/).length > 1;
  }

  function highlightVerse(o) {
    const text = String(o.verse_text || "");
    const start = Number(o.start_offset);
    const end = Number(o.end_offset);

    if (
      Number.isInteger(start) &&
      Number.isInteger(end) &&
      start >= 0 &&
      end > start &&
      end <= text.length
    ) {
      return (
        esc(text.slice(0, start)) +
        "<mark>" + esc(text.slice(start, end)) + "</mark>" +
        esc(text.slice(end))
      );
    }

    return esc(text);
  }

  function filtered() {
    const q = foldSearch($("search").value);
    const type = $("typeFilter").value;

    const scored = [];

    for (const d of state.descriptors) {
      if (type === "one" && isMulti(d)) continue;
      if (type === "multi" && !isMulti(d)) continue;

      const score = searchScore(q, d);
      if (score < 0) continue;
      scored.push({ d, score });
    }

    if (q) {
      scored.sort((a, b) =>
        b.score - a.score ||
        Number(b.d.combined_occurrence_count || 0) - Number(a.d.combined_occurrence_count || 0) ||
        String(a.d.transliteration || a.d.lexical_identity_arabic).localeCompare(
          String(b.d.transliteration || b.d.lexical_identity_arabic)
        )
      );
    }

    return scored.map(x => x.d);
  }

  function renderList() {
    const list = filtered();
    $("listCount").textContent = `${list.length} / ${state.descriptors.length}`;

    $("descriptorList").innerHTML = list.length
      ? list.map(d => `
          <button
            class="descriptor-item ${state.selected === d.lexical_identity_arabic ? "active" : ""}"
            data-id="${esc(d.lexical_identity_arabic)}"
            type="button">
            <span class="descriptor-copy">
              <span class="descriptor-ar">${esc(d.preferred_quran_surface || d.lexical_identity_arabic)}</span>
              <span class="descriptor-tr">${esc(d.transliteration || "")}</span>
              <span class="descriptor-meaning">${esc(d.english_gloss || "")}</span>
            </span>
            <span class="count-pill">${Number(d.combined_occurrence_count || 0).toLocaleString()}</span>
          </button>
        `).join("")
      : '<div class="empty-state">No matches.</div>';

    document.querySelectorAll(".descriptor-item").forEach(btn => {
      btn.addEventListener("click", () => {
        select(btn.dataset.id);
        closeSidebar();
      });
    });
  }

  function formArabic(f) {
    return f?.display_arabic || f?.form_arabic || f?.headword_arabic || f?.qac_lemma_arabic || "";
  }

  function formDescription(f) {
    return f?.public_pos_label || f?.public_morphology_hint || f?.lexical_class || f?.part_of_speech || f?.form_label || "";
  }

  function descriptorRootSummary(d, occs) {
    const links = occs
      .map(o => state.rootByOccurrence.get(o.occurrence_id))
      .filter(Boolean);

    if (!links.length) return "";

    if (!isMulti(d)) {
      const unique = new Map();

      for (const link of links) {
        if (link.scope !== "one_word") continue;

        for (const f of link.public_forms || []) {
          const rootId = f?.root_id || "";
          const publicFormId = f?.public_form_id || f?.form_id || "";
          const key = `${rootId}|${publicFormId}`;
          if (!unique.has(key)) unique.set(key, f);
        }
      }

      if (!unique.size) return "";

      const cards = [...unique.values()].map(f => {
        const url = f?.pray_for_the_truth_root_url ||
          (f?.root_id ? `https://prayforthetruth.com/root/${encodeURIComponent(f.root_id)}` : "");
        const rootAr = f?.root_arabic || "";
        const head = formArabic(f);
        const pos = formDescription(f);
        const count = f?.root_dictionary_occurrence_count;

        return `
          <div class="descriptor-root-card">
            <div class="descriptor-root-head">
              ${rootAr ? `<span class="descriptor-root-arabic">${esc(rootAr)}</span>` : ""}
              ${head ? `<span class="root-word">${esc(head)}</span>` : ""}
            </div>
            <div class="descriptor-root-meta">
              ${pos ? `<div><strong>Form:</strong> ${esc(pos)}</div>` : ""}
              ${Number.isFinite(Number(count))
                ? `<div><strong>Occurrences of this form in the root dictionary:</strong> ${Number(count).toLocaleString()}</div>`
                : ""}
            </div>
            ${url
              ? `<a class="btn primary root-dictionary-link" target="_blank" rel="noopener noreferrer" href="${esc(url)}">Open full root dictionary ↗</a>`
              : ""}
          </div>
        `;
      }).join("");

      return `
        <section class="section">
          <div class="section-head">
            <h2>Root dictionary</h2>
            <div class="section-sub">Exact one-word Quran Roots linkage</div>
          </div>
          <div class="section-body">
            <div class="descriptor-root-grid">${cards}</div>
          </div>
        </section>
      `;
    }

    const uniqueRoots = new Map();

    for (const link of links) {
      if (link.scope !== "multiword") continue;

      for (const word of link.constituent_words || []) {
        for (const r of word.roots || []) {
          const rootId = r?.root_id || "";
          const key = rootId || r?.root || r?.root_arabic || "";
          if (!key || uniqueRoots.has(key)) continue;

          const descriptions = [];
          for (const fg of r?.form_groups || []) {
            const label =
              fg?.public_pos_label ||
              fg?.public_morphology_hint ||
              fg?.lexical_class ||
              "";
            if (label && !descriptions.includes(label)) descriptions.push(label);
          }

          uniqueRoots.set(key, {
            root_id: rootId,
            root_arabic: r?.root_arabic || "",
            root_code: r?.root || "",
            descriptions,
          });
        }
      }
    }

    if (!uniqueRoots.size) return "";

    const cards = [...uniqueRoots.values()].map(r => {
      const url = r.root_id
        ? `https://prayforthetruth.com/root/${encodeURIComponent(r.root_id)}`
        : "";
      const rootLabel = r.root_arabic || r.root_code || "Root";

      return `
        <div class="descriptor-root-card">
          <div class="descriptor-root-head">
            <span class="descriptor-root-arabic">${esc(rootLabel)}</span>
          </div>
          <div class="descriptor-root-meta">
            ${r.descriptions.length
              ? `<div><strong>Forms represented in this phrase:</strong> ${r.descriptions.map(esc).join(" · ")}</div>`
              : ""}
          </div>
          ${url
            ? `<a class="btn primary root-dictionary-link" target="_blank" rel="noopener noreferrer" href="${esc(url)}">Open this root in the Quran Roots Dictionary ↗</a>`
            : ""}
        </div>
      `;
    }).join("");

    return `
      <section class="section">
        <div class="section-head">
          <h2>Roots in this phrase</h2>
          <div class="section-sub">Constituent roots; the phrase remains one descriptor</div>
        </div>
        <div class="section-body">
          <div class="descriptor-root-grid">${cards}</div>
        </div>
      </section>
    `;
  }

  function occurrenceHtml(o) {
    const loc = o.record_type === "opening_basmala_unnumbered"
      ? o.source_key
      : o.verse_key;

    const quranLink = o.record_type === "opening_basmala_unnumbered"
      ? ""
      : `<a class="btn primary" target="_blank" rel="noopener noreferrer"
            href="https://prayforthetruth.com/quran/${esc(String(o.verse_key || "").replace(":", "/"))}">
           Read verse with English translation ↗
         </a>`;

    return `
      <article class="occ">
        <div class="occ-head">
          <div class="verse-key">${esc(loc)}</div>
          <div class="surface-hit">${esc(o.surface_arabic)}</div>
          <div class="occ-id">${esc(o.occurrence_id)}</div>
        </div>
        <div class="verse-panel">
          <div class="verse-ar">${highlightVerse(o)}</div>
          ${quranLink ? `<div style="margin-top:12px">${quranLink}</div>` : ""}
        </div>
      </article>
    `;
  }

  function renderDetail() {
    const d = state.descriptors.find(x => x.lexical_identity_arabic === state.selected);
    if (!d) {
      $("detail").innerHTML = '<div class="empty-state">Select a descriptor to inspect its Quran evidence.</div>';
      return;
    }

    const occs = state.occurrenceByIdentity.get(d.lexical_identity_arabic) || [];
    const visible = occs.slice(0, state.visibleOccurrences);

    const surfaces = (d.numbered_member_surfaces || [])
      .map(s => `<span class="surface">${esc(s)}</span>`)
      .join("");

    $("detail").innerHTML = `
      <header class="descriptor-header">
        <h2 class="title-ar">${esc(d.preferred_quran_surface || d.lexical_identity_arabic)}</h2>
        <div class="title-tr">${esc(d.transliteration || "")}</div>
        <div class="title-meaning"><span class="title-meaning-label">English meaning</span>${esc(d.english_gloss || "")}</div>
      </header>

      <section class="stats" aria-label="Descriptor statistics">
        <div class="stat">
          <div class="k">In numbered verses</div>
          <div class="v">${Number(d.numbered_occurrence_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Opening basmalas</div>
          <div class="v">${Number(d.basmala_occurrence_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Total occurrences</div>
          <div class="v">${Number(d.combined_occurrence_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Arabic forms</div>
          <div class="v">${Number(d.exact_numbered_surface_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Expression type</div>
          <div class="v">${isMulti(d) ? "Multiword phrase" : "Single word"}</div>
        </div>
      </section>

      ${descriptorRootSummary(d, occs)}

      <section class="section">
        <div class="section-head">
          <h2>Arabic forms found in the Quran</h2>
          <div class="section-sub">Exact forms of this descriptor in numbered verses</div>
        </div>
        <div class="section-body">
          <div class="surface-wrap">${surfaces || '<span class="small">No numbered-verse forms.</span>'}</div>
          <div class="surface-explainer">These chips preserve the exact Arabic form used in the Quran. The same descriptor can appear with different case endings, attached particles, or orthographic forms.</div>
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <h2>Where it occurs in the Quran</h2>
          <div class="section-sub">${occs.length.toLocaleString()} occurrences, including preserved opening basmalas</div>
        </div>
        <div class="section-body">
          <div class="occ-list">${visible.map(occurrenceHtml).join("")}</div>
          ${visible.length < occs.length ? `
            <div class="more-row">
              <button id="showMore" class="btn" type="button">
                Show ${Math.min(PAGE_SIZE, occs.length - visible.length)} more
              </button>
            </div>
          ` : ""}
        </div>
      </section>
    `;

    const more = $("showMore");
    if (more) {
      more.addEventListener("click", () => {
        state.visibleOccurrences += PAGE_SIZE;
        renderDetail();
      });
    }
  }

  function select(identity) {
    state.selected = identity;
    state.visibleOccurrences = PAGE_SIZE;
    renderList();
    renderDetail();
  }

  function openSidebar() {
    $("sidebar").classList.add("open");
  }

  function closeSidebar() {
    $("sidebar").classList.remove("open");
  }

  async function load() {
    const [d, o, r, v] = await Promise.all([
      fetch("./data/descriptors.json").then(x => x.json()),
      fetch("./data/occurrence_ledger.json").then(x => x.json()),
      fetch("./data/root_links.json").then(x => x.json()),
      fetch("./data/validation_report.json").then(x => x.json()),
    ]);

    state.descriptors = d.descriptors || [];

    for (const row of o.occurrences || []) {
      const key = row.lexical_identity_arabic;
      if (!state.occurrenceByIdentity.has(key)) {
        state.occurrenceByIdentity.set(key, []);
      }
      state.occurrenceByIdentity.get(key).push(row);
    }

    for (const link of r.links || []) {
      state.rootByOccurrence.set(link.occurrence_id, link);
    }

    const expected = Number(v?.counts?.lexical_identities || 0);
    if (expected && state.descriptors.length !== expected) {
      throw new Error(
        `Descriptor count mismatch: viewer loaded ${state.descriptors.length}, validation expects ${expected}.`
      );
    }

    $("loading").hidden = true;
    $("app").hidden = false;

    renderList();

    if (state.descriptors.length) {
      select(state.descriptors[0].lexical_identity_arabic);
    }
  }

  $("search").addEventListener("input", renderList);
  $("typeFilter").addEventListener("change", renderList);
  $("openSidebar").addEventListener("click", openSidebar);
  $("closeSidebar").addEventListener("click", closeSidebar);

  load().catch(err => {
    console.error(err);
    $("loading").innerHTML = `
      <div class="fatal">
        <strong>Could not load publication data.</strong>
        <div class="small" style="margin-top:8px">${esc(err.message)}</div>
      </div>
    `;
  });
})();
'''


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument(
        "--license-source",
        type=Path,
        default=Path.home() / "Projects/quran-roots-dictionary/LICENSE",
        help="Path to the existing GPL-3.0-only LICENSE file used by the sibling Quran Roots repository.",
    )
    a = ap.parse_args()
    repo = a.repo.resolve()
    target = a.target.expanduser().resolve()
    license_source = a.license_source.expanduser().resolve()

    freeze = repo / "final/publication_v1"
    report = load(freeze / "validation_report.json")
    if report.get("status") != "PASS" or report.get("publication_final") is not True:
        raise SystemExit("Publication freeze is not PASS/publication_final.")

    if not license_source.exists():
        raise SystemExit(
            f"GPL LICENSE source not found: {license_source}\n"
            "Pass --license-source pointing to the verified GPL-3.0 license file."
        )

    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"Target is not empty; refusing to overwrite: {target}")
    target.mkdir(parents=True, exist_ok=True)

    data = target / "data"
    scripts = target / "scripts"
    docs = target / "docs"
    assets = target / "assets"
    for d in (data, scripts, docs, assets):
        d.mkdir()

    for name in PUBLIC_DATA_FILES:
        src = freeze / name
        if not src.exists():
            raise SystemExit(f"Missing publication artifact: {src}")
        shutil.copy2(src, data / name)

    # Copy project pipeline code, but not runs/raw API payloads or local viewer data.
    for src in sorted((repo / "scripts").glob("*.py")):
        shutil.copy2(src, scripts / src.name)

    selected_docs = [
        "PHASE1_SURGICAL_CLEANUP_V1.md",
        "PHASE2_GLOBAL_AUDIT_SOL_V3.md",
        "SEMANTIC_EXCLUSIONS_V1_2026-09-13.md",
        "ROOT_FORM_BUILDER_V1_4_EXACT_QAC_SURFACE_PATCH_2026-09-13.md",
        "FINALIZATION_RUNBOOK_2026-09-22.md",
    ]
    for name in selected_docs:
        src = repo / "docs" / name
        if src.exists():
            shutil.copy2(src, docs / name)

    # Verified GPL text from sibling repository.
    shutil.copy2(license_source, target / "LICENSE")

    (target / "README.md").write_text(README + "\n", encoding="utf-8")
    (target / "LICENSE_SCOPE.md").write_text(LICENSE_SCOPE + "\n", encoding="utf-8")
    (target / "THIRD_PARTY_NOTICES.md").write_text(THIRD_PARTY + "\n", encoding="utf-8")
    (data / "DATA_LICENSE.md").write_text(DATA_LICENSE + "\n", encoding="utf-8")
    (docs / "LICENSING.md").write_text(LICENSING + "\n", encoding="utf-8")
    (docs / "SOURCE_PROVENANCE.md").write_text(SOURCE_PROVENANCE + "\n", encoding="utf-8")
    (docs / "PUBLIC_RELEASE_BOUNDARY.md").write_text(PUBLIC_BOUNDARY + "\n", encoding="utf-8")
    (target / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (target / ".nojekyll").write_text("", encoding="utf-8")

    # Self-contained GitHub Pages viewer using only publication-final public data.
    (target / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (assets / "styles.css").write_text(STYLES, encoding="utf-8")
    (assets / "app.js").write_text(APP_JS, encoding="utf-8")

    # Public release provenance marker.
    release_meta = {
        "release": "publication-v1",
        "pages_viewer": True,
        "viewer_data_source": "data/ publication-final JSON only",
        "quran_foundation_raw_content_included": False,
        "english_verse_translation_payloads_included": False,
        "project_derived_descriptor_glosses_included": True,
        "project_derived_transliterations_included": True,
        "license": "GPL-3.0-only for project-owned material; third-party layers retain upstream terms",
    }
    (target / "PUBLIC_RELEASE.json").write_text(
        json.dumps(release_meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("GITHUB PUBLIC RELEASE STAGING: PASS")
    print(f"Target: {target}")
    print("GitHub Pages viewer: dark research-viewer design v6 (descriptor-level roots only, no technical IDs, English meanings, fuzzy search)")
    print("LICENSE: copied from verified sibling Quran Roots repository")
    print("QF raw/API content: excluded")
    print("Project descriptor glosses/transliterations: included")
    print("No Git repository was initialized and nothing was pushed.")


if __name__ == "__main__":
    main()
