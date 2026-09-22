# Source provenance

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

