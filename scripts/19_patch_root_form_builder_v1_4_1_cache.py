#!/usr/bin/env python3
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

REPO = Path.home() / "Projects" / "PFTT" / "names_of_Allah"
TARGET = REPO / "descriptor_viewer" / "scripts" / "build_descriptor_root_forms.py"

if not TARGET.exists():
    raise SystemExit(f"ERROR: builder not found: {TARGET}")

text = TARGET.read_text(encoding="utf-8")

if 'VERSION = "1.4.1"' in text and "from functools import lru_cache" in text:
    print("Builder already carries the v1.4.1 performance cache patch.")
    raise SystemExit(0)

required_markers = [
    'VERSION = "1.4"',
    "def lexical_token_spans(",
    "def normalize_quran_surface(",
    "def normalize_quran_surface_vocalized(",
    "def vocalized_surface_variants(",
    "def surface_variants(",
    "def qac_surface_match_score(",
]
missing = [m for m in required_markers if m not in text]
if missing:
    raise SystemExit(
        "ERROR: current builder does not match the expected validated v1.4 source.\n"
        "Refusing to patch.\nMissing markers:\n  " + "\n  ".join(missing)
    )

stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
archive_dir = (
    REPO
    / "archive"
    / "root_form_enrichment"
    / f"builder_v1_4_before_perf_cache_{stamp}"
)
archive_dir.mkdir(parents=True, exist_ok=False)
backup = archive_dir / TARGET.name
shutil.copy2(TARGET, backup)

# Import cache helper.
anchor = "from collections import Counter, defaultdict\n"
replacement = anchor + "from functools import lru_cache\n"
if replacement not in text:
    if text.count(anchor) != 1:
        raise SystemExit("ERROR: unexpected collections import layout; refusing to patch.")
    text = text.replace(anchor, replacement, 1)

# Performance-only memoization. All decorated functions are pure for a given
# argument tuple in v1.4. Their returned collections are only iterated/read.
functions = [
    "lexical_token_spans",
    "normalize_quran_surface",
    "normalize_quran_surface_vocalized",
    "vocalized_surface_variants",
    "surface_variants",
    "qac_surface_match_score",
]

for name in functions:
    marker = f"def {name}("
    decorated = f"@lru_cache(maxsize=None)\n{marker}"
    if decorated in text:
        continue
    if text.count(marker) != 1:
        raise SystemExit(
            f"ERROR: expected exactly one {marker!r}, found {text.count(marker)}; "
            "refusing to patch."
        )
    text = text.replace(marker, decorated, 1)

# Record this as a performance-only revision.
text = text.replace('VERSION = "1.4"', 'VERSION = "1.4.1"', 1)

doc_anchor = "Version 1.4 changes the join contract:\n"
doc_replacement = (
    "Version 1.4.1 is a performance-only revision of validated v1.4. "
    "It memoizes pure Quran-surface normalization/scoring helpers; "
    "matching rules and output semantics are unchanged.\n\n"
    "Version 1.4 changes the join contract:\n"
)
if doc_anchor in text and "Version 1.4.1 is a performance-only revision" not in text:
    text = text.replace(doc_anchor, doc_replacement, 1)

TARGET.write_text(text, encoding="utf-8")

print("PATCHED: root-form builder v1.4 -> v1.4.1 (performance-only)")
print(f"Builder: {TARGET}")
print(f"Backup:  {backup}")
print("Caching added to:")
for name in functions:
    print(f"  {name}")
