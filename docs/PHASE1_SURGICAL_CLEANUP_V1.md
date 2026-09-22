# Phase 1 surgical cleanup v1

This replaces the attempted generalized integrity rebuild.

It starts from the already-frozen Phase-1 PASS outputs in `resolved_attempts/`.
It does not re-run or reinterpret the model and does not contain an Allah
substring detector.

It applies only six evidence-backed verse-level corrections found by comparing
the original ledger with the corrected Quran surfaces:

- 6:39 remove `لِلْهُ`
- 10:59 replace malformed `للَّهُ` with exact Quran `آللَّهُ`
- 27:59 replace malformed `للَّهُ` with exact Quran `آللَّهُ`
- 62:11 remove `اللَّهْوِ`
- 77:31 remove `اللَّهَبِ`
- 92:12 remove `لَلْهُدَىٰ`

It then applies the already-frozen four manual-review exclusions.

Every remaining descriptor is validated only by simple rules:
- it must be an exact contiguous substring of the Quran verse;
- duplicates may not exceed literal source occurrences;
- descriptor order must be left-to-right.

Nothing else is inferred or repaired.

Expected clean totals:
- 5,117 descriptor occurrences
- 446 exact surfaces
- 0 unresolved manual-review occurrences
- 446 Phase-2 input surfaces

No API call is made and no prior artifact is overwritten.
