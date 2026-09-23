# Method

## Names & Descriptors of Allah in the Quran

This project was designed to answer a deliberately Quran-first question:

> **What names and explicit descriptive expressions does the Quran itself use for Allah when the Quran is examined without beginning from a pre-existing list of divine names?**

It is therefore **not** a reconstruction of a traditional “99 Names of Allah” list, and no classical or traditional list of divine names was supplied to the extraction system as a seed, checklist, or authority for deciding what should appear.

The corpus records explicit Quranic language first and only later groups, reviews, and enriches that evidence.

## Why the project uses the word “descriptors”

“Names” alone would be too narrow for the research question and would import a later theological category into the extraction step.

The Quran refers to or describes Allah using several kinds of expressions, including:

- proper or name-like expressions;
- nouns;
- adjectives;
- active or other participles;
- nominal and adjectival phrases;
- multiword expressions.

The project therefore uses **descriptor** as a broad research term for explicit Quranic expressions that refer to or describe Allah in context.

Inclusion in this corpus does **not** by itself mean that an expression is being declared a formal theological “Name of Allah.”

Finite verbs are not converted into inferred descriptors merely because they describe something Allah does. The project records explicit referential/descriptive language rather than attributes inferred from actions.

---

## 1. Quran source and preprocessing

The frozen source text is `quran-simple-plain.json`.

Source checksum:

`10b63cb29e329de93f80ff60eb332e52b3a72be8f68f6eb6272a03d4cb16084c`

The source contains:

- 114 surahs;
- 6,236 canonical numbered ayahs;
- 112 preserved opening basmalas stored separately as `ayah:0`.

The 112 `ayah:0` basmalas were deliberately **excluded from the model-assisted extraction stage**. They were retained in the source and added later by a deterministic augmentation step after the lexical system had been frozen.

Preprocessing also avoided cross-surah context leakage. Long-surah endings were not combined with the beginning of the next surah merely to fill a packet.

Key script:

- [`01_prepare_allah_name_packets.py`](../scripts/01_prepare_allah_name_packets.py)

---

## 2. Phase 1 — Quran-only extraction

Phase 1 used model-assisted extraction to inspect the Quran verse by verse and identify explicit expressions referring to or describing Allah.

Key script:

- [`02_openai_batch_allah_names_phase1.py`](../scripts/02_openai_batch_allah_names_phase1.py)

The extraction prompt was intentionally constrained.

### No traditional-name seed

The model was not given a traditional list of the 99 Names as a target inventory.

The purpose was to avoid confirmation bias: a seeded list could cause the system to look for expected names rather than identify the Quran's own descriptive language independently.

### Exact Quran surface required

Every finding had to preserve the exact Arabic surface appearing in the source verse.

The system was not asked to invent a citation form, dictionary headword, or normalized Arabic form during extraction.

Attached suffixes remain part of the extracted Quran surface when they belong to the expression. External clitics could only be excluded when the remaining span was still a literal exact substring of the verse.

### Referential context

Context could establish that an expression referred to Allah, including where pronouns or surrounding discourse resolved the referent.

However:

- pronouns themselves were not descriptors;
- generic terms referring to someone other than Allah were excluded;
- `رب` used for a non-divine master was excluded;
- `إله` used for false gods was excluded;
- an expression appearing inside a quotation or claim about Allah was not automatically treated as a true descriptor of Allah.

### Grammatical scope

The extraction targeted explicit:

- nouns;
- adjectives;
- participles;
- nominal expressions;
- adjectival expressions.

Finite verbs were not transformed into inferred nominal attributes.

Distinct derivational or lexical forms were not collapsed merely because they shared a root.

Genuine multiword expressions were allowed to remain multiword.

### Per-occurrence evidence

Findings were occurrence-based. Each retained occurrence carried its Quran location, exact surface, context, and occurrence identity so later decisions could be audited at the individual-verse level.

---

## 3. Phase 1 structural validation and finalization

The model output was not accepted directly as the corpus.

It was subjected to deterministic checks for:

- exact substring validity;
- occurrence indexing;
- verse/location validity;
- schema validity;
- duplicate or conflicting findings;
- unresolved manual-review cases.

Key finalization script:

- [`03_finalize_phase1.py`](../scripts/03_finalize_phase1.py)

The final clean Phase-1 corpus contained:

- 5,117 descriptor occurrences;
- 446 exact Quran surfaces;
- zero unresolved manual-review items.

A small set of structural/semantic mistakes discovered during review was corrected surgically rather than by rerunning or rewriting the Quran source.

Examples included false substring matches such as pieces of unrelated words and cases where an expression initially appeared plausible but did not function as a divine descriptor in context.

Historical raw responses and request metadata were preserved in the private research provenance.

---

## 4. Phase 2 — lexical normalization

Phase 1 answers:

> What exact expression occurred here?

Phase 2 asks a different question:

> Which occurrences belong to the same abstract lexical identity?

The project therefore separates:

`exact Quran occurrence → exact Quran surface → lexical identity`

This distinction is fundamental.

For example, different case endings or orthographic realizations may represent the same lexical identity while still remaining separately preserved as exact Quran surfaces.

Key inventory script:

- [`04_build_phase2_inventory.py`](../scripts/04_build_phase2_inventory.py)

A global lexical audit then reviewed the proposed surface-to-identity mapping across the entire corpus.

The reviewed Phase-2 state contained:

- 255 lexical identities;
- 5,117 occurrences;
- 446 exact surfaces.

One example of why surface and identity are kept separate is `الْمُتَعَالِ`: the Quran surface remains unchanged, while its abstract lexical identity was corrected from `مُتَعَال` to `مُتَعَالِي`.

---

## 5. Semantic review and semantic-exclusions v1

Structural validity is not sufficient for semantic validity.

A dedicated semantic pass reviewed whether expressions that had survived extraction should actually belong in the Quranic descriptor corpus.

Key builder:

- [`16_build_semantic_exclusions_v1.py`](../scripts/16_build_semantic_exclusions_v1.py)

Important exclusion categories included:

### Negated or denied predicates

Expressions were excluded where the Quran explicitly denied the predicate of Allah rather than asserting it.

Examples include categories represented by terms such as:

- unjust;
- forgetful;
- heedless.

### False claims attributed to opponents

A statement such as an opponent's claim that Allah is poor is not accepted as a Quranic descriptor merely because the words “Allah” and “poor” occur in the same reported speech.

### Non-referential or relational expressions

Some expressions occur in relation to Allah but do not themselves function as referential descriptors.

### Possessed abstractions

Abstract qualities or possessions were reviewed separately from expressions that directly name or describe Allah.

### Body-part expressions

Terms such as hand, eye, and face were excluded from the descriptor identity inventory under the project's final semantic policy rather than being automatically turned into divine names/descriptors.

### Relational ordinals

Expressions such as “fourth” or “sixth” in rhetorical descriptions of divine presence were not treated as divine ordinal names.

### Over-general action labels

Highly generic participial/action labels were reviewed for whether they functioned as meaningful lexical descriptors rather than merely reflecting a grammatical action.

Semantic-exclusions v1 produced:

- 233 retained lexical identities;
- 5,067 retained occurrences;
- 415 retained exact surfaces.

It excluded 22 identities representing 50 occurrences and 31 exact surfaces.

Historical Phase-2 files were preserved unchanged.

---

## 6. Precision/recall review and semantic-exclusions v2

The v1 corpus was then reviewed again for both precision and recall.

This review operated at two levels:

1. whole lexical identities;
2. individual occurrences within otherwise valid identities.

Key builder:

- [`18_build_semantic_exclusions_v2.py`](../scripts/18_build_semantic_exclusions_v2.py)

### Identity-level review

Eight additional lexical identities were excluded in v2, representing 12 numbered occurrences.

These included cases such as:

- negated or conditioned predicates;
- adverbial exclusivity rather than a descriptor;
- possessed abstract qualities;
- possessed domains rather than referential descriptors.

### Occurrence-level review of `إِلَـٰه`

The simple lexical identity `إِلَـٰه` required occurrence-by-occurrence review.

The rule used was **direct referent**, not merely presence in a theological formula.

Twenty occurrences were retained where the token directly referred to Allah.

Eighteen were removed where the word functioned generically under negation or exclusivity rather than as the direct divine referent.

This is an example of why occurrence-level review was necessary even after lexical normalization.

### Phrase-boundary corrections

Two one-word identities were replaced by Quranically complete phrases:

- `عَدُوّ` → `عَدُوّ لِلْكَافِرِينَ`
- `أَوْفَىٰ` → `أَوْفَىٰ بِعَهْدِهِ`

The old identities do not coexist with the corrected phrase identities in publication v1, but their history remains preserved in review provenance.

### Final semantic-v2 result

Semantic-exclusions v2 contains:

- **225 lexical identities**
- **5,037 numbered occurrences**
- **404 exact numbered-verse surfaces**

This is the semantic source for publication v1.

---

## 7. Preferred Quran-attested display forms

The lexical identity is not necessarily the Arabic string best suited for public display.

However, the project does not synthesize an unattested Arabic display form.

Each lexical identity receives a `preferred_quran_surface` selected only from its retained exact Quran surfaces.

Key script:

- [`21_build_preferred_quran_surfaces_v1.py`](../scripts/21_build_preferred_quran_surfaces_v1.py)

The deterministic selection rule is:

1. choose the most frequent retained numbered-verse surface;
2. break a frequency tie by earliest Quran occurrence;
3. use Unicode order only as the final deterministic tie-break.

Thus:

`lexical identity ≠ exact occurrence surface ≠ preferred public display form`

but every preferred Arabic display form is Quran-attested.

---

## 8. One-word root and morphology linkage

After the semantic corpus was frozen, one-word descriptors were linked to the Quran Roots/Quranic Arabic Corpus morphology data.

This enrichment did **not** determine whether an expression belonged in the descriptor corpus. It was added after semantic inclusion decisions.

The linkage principle was:

`retained Quran occurrence → exact same-verse QAC occurrence → exact QAC form group → Quran Roots public form/root`

Roots were never inferred from visible Arabic spelling.

The final one-word enrichment contains:

- 125 one-word lexical identities;
- 4,798 one-word numbered occurrences;
- 4,798 / 4,798 occurrences exactly linked;
- zero partial matches;
- zero unmatched occurrences.

The validated builder reached version 1.4.1 after a performance-only memoization patch. The matching semantics were unchanged by that optimization.

The public corpus carries the resulting root/form evidence and direct links to the Quran Roots Dictionary.

---

## 9. Multiword constituent/root linkage

Multiword descriptors remain **one semantic descriptor**.

They are not split into multiple descriptor identities simply because their constituent words have different roots.

The root-link layer instead records constituent evidence beneath the intact phrase.

Key script:

- [`22_build_multiword_root_links_v1.py`](../scripts/22_build_multiword_root_links_v1.py)

The final v1.1 bridge uses:

`descriptor verse + exact source offsets → source token sequence → stable Quran word location → QAC root-bearing segment → exact Quran Roots form group`

The initial positional bridge exposed a small alignment offset in nine occurrences. Version 1.1 retained the exact-ID principle but added a strict fallback:

- search only within the same verse;
- require the full descriptor token sequence to match a contiguous Quran word sequence;
- accept the fallback only when the match is unique;
- after alignment, obtain roots only from the existing QAC/Quran Roots identifiers.

No fuzzy root inference was introduced.

Final multiword linkage:

- 100 multiword lexical identities;
- 239 numbered occurrences;
- 239 / 239 occurrences linked;
- zero unresolved occurrences.

---

## 10. Deterministic basmala augmentation

The 112 opening basmalas preserved as `ayah:0` were intentionally not sent through Phase 1.

After the semantic and lexical system was frozen, they were added deterministically.

Key script:

- [`23_build_basmala_augmentation_v1.py`](../scripts/23_build_basmala_augmentation_v1.py)

The augmentation performs exact full-token lookup against the finalized surface-to-identity mapping.

It creates no new lexical identity.

Each of the 112 basmalas contributes exactly:

- `اللَّه`
- `رَحْمَـٰن`
- `رَحِيم`

for:

- 112 × `اللَّه`
- 112 × `رَحْمَـٰن`
- 112 × `رَحِيم`
- **336 total basmala descriptor occurrences**

Because the QAC numbered-verse morphology source does not provide these `ayah:0` records, the publication explicitly records their QAC root link as unavailable rather than fabricating one.

Numbered-verse counts and `ayah:0` counts remain separately identifiable.

---

## 11. Publication freeze

Publication v1 is built only after semantic, display-form, root-link, and basmala validation succeeds.

Key script:

- [`24_build_publication_freeze_v1.py`](../scripts/24_build_publication_freeze_v1.py)

The publication freeze validates, among other things:

- immutable Quran source checksum;
- reconciled semantic-review state;
- identity and occurrence counts;
- uniqueness of occurrence IDs;
- exact Quran attestation of preferred display forms;
- complete one-word root linkage;
- complete multiword constituent/root linkage;
- explicit null QAC linkage for `ayah:0`;
- absence of basmala-created semantic identities;
- descriptor transliteration and English gloss coverage;
- public Quran Roots Dictionary URLs for one-word root links.

Publication v1 contains:

- **225** reviewed lexical identities;
- **5,037** numbered-verse occurrences;
- **404** exact numbered-verse surfaces;
- **336** preserved-basmala descriptor occurrences;
- **5,373** combined descriptor occurrences;
- **4,798** one-word numbered occurrences with root/form linkage;
- **239** multiword numbered occurrences with constituent/root linkage.

Machine-readable release assertions are in:

- [`../data/validation_report.json`](../data/validation_report.json)
- [`../data/manifest.json`](../data/manifest.json)

---

## 12. Public-release construction and validation

The public GitHub repository is not the private working directory.

The private research project contains raw runs, archives, review provenance, intermediate artifacts, and local viewer resources.

The public release is staged separately from the frozen publication artifacts.

Key scripts:

- [`25_build_github_public_release_v1.py`](../scripts/25_build_github_public_release_v1.py)
- [`26_validate_github_public_release_v1.py`](../scripts/26_validate_github_public_release_v1.py)

The public builder copies only the intended release artifacts and generates the static GitHub Pages viewer.

The validator checks both data integrity and important viewer/publication invariants.

---

## 13. Public-data boundary and licensing

The public repository includes:

- publication-final descriptor data;
- exact retained Quran surfaces and Arabic verse context;
- project-derived transliterations;
- project-derived concise English descriptor meanings/glosses;
- exclusion/review history;
- one-word root/form evidence;
- multiword constituent/root evidence;
- build/release scripts;
- method and provenance documentation.

It intentionally does not redistribute:

- raw Quran Foundation/Quran.com API content;
- private/local API response payloads;
- local full-verse English translation files without separately established redistribution rights;
- private run directories and archives.

The Arabic Quran text is Tanzil-derived and retains its upstream terms and attribution requirements.

Quranic Arabic Corpus-derived morphology retains the licensing caveat documented in this repository.

Project-owned material is offered under GPL-3.0-only to the extent the project controls the relevant rights.

See:

- [`../LICENSE_SCOPE.md`](../LICENSE_SCOPE.md)
- [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)
- [`DATA_LICENSE.md`](DATA_LICENSE.md)
- [`LICENSING.md`](LICENSING.md)
- [`SOURCE_PROVENANCE.md`](SOURCE_PROVENANCE.md)

---

## 14. Role of model assistance and human/deterministic review

The model was used as a bounded extraction and audit component, not as an unquestioned source of truth.

The pipeline deliberately separates:

1. model-assisted candidate extraction;
2. deterministic structural validation;
3. lexical normalization;
4. global audit;
5. semantic review;
6. occurrence-level adjudication where necessary;
7. deterministic enrichment;
8. publication validation.

Raw model responses and request metadata were preserved in the private research provenance.

The Quran text itself was never rewritten to accommodate a model output.

---

## 15. What this corpus does and does not claim

This corpus is intended as a reproducible Quran-based research dataset.

It claims to document the result of the project's explicit inclusion policy:

- Quran-first;
- no traditional divine-name list as seed;
- explicit referential/descriptive language;
- preserved occurrence evidence;
- reviewed lexical identities;
- transparent exclusions and corrections.

It does **not** claim that every retained descriptor is thereby a formal theological divine name.

It also does not claim that a later traditional classification is invalid. Traditional name lists can be compared with this corpus **after** the Quran-only corpus has been frozen, but they were deliberately not allowed to define the extraction target.

That separation is central to the method.
