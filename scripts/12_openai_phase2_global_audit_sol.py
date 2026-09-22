#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "high"
MAX_OUTPUT_TOKENS = 12_000
SCHEMA_NAME = "names_of_allah_phase2_global_mapping_audit_v1"

PRIVATE_ENV_OVERRIDE_VAR = "NAMES_OF_ALLAH_ENV_FILE"
DEFAULT_PRIVATE_ENV = (
    Path.home() / "Projects" / "PFTT" / "SOURCES" / "quran-roots" / ".env"
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def plain(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def load_api_key() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return

    env_path = Path(
        os.environ.get(PRIVATE_ENV_OVERRIDE_VAR, DEFAULT_PRIVATE_ENV)
    ).expanduser()

    if not env_path.is_file():
        raise RuntimeError(
            f"OPENAI_API_KEY is not set and private .env was not found: "
            f"{env_path}"
        )

    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        if key.strip() != "OPENAI_API_KEY":
            continue

        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        if not value:
            raise RuntimeError(f"OPENAI_API_KEY is empty in {env_path}")

        os.environ["OPENAI_API_KEY"] = value
        return

    raise RuntimeError(f"OPENAI_API_KEY not found in {env_path}")


def response_output_text(raw: dict[str, Any]) -> str | None:
    direct = raw.get("output_text")
    if isinstance(direct, str) and direct:
        return direct

    pieces = []
    for item in raw.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if (
                isinstance(content, dict)
                and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ):
                pieces.append(content["text"])

    return "".join(pieces) if pieces else None


def build_groups(
    mappings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    groups: OrderedDict[str, list[str]] = OrderedDict()

    for row in mappings:
        groups.setdefault(row["lexical_identity_arabic"], [])
        groups[row["lexical_identity_arabic"]].append(
            row["surface_arabic"]
        )

    return [
        {
            "lexical_identity_arabic": identity,
            "member_surfaces": members,
        }
        for identity, members in groups.items()
    ]


def assert_core_invariants(
    mapping_by_surface: dict[str, str],
) -> None:
    allah_surfaces = [
        "اللَّهُ",
        "اللَّهَ",
        "اللَّهِ",
        "لِلَّهِ",
        "آللَّهُ",
    ]
    present_allah = [
        x for x in allah_surfaces
        if x in mapping_by_surface
    ]
    for surface in present_allah:
        if mapping_by_surface[surface] != "اللَّه":
            raise RuntimeError(
                f"Allah invariant failed: {surface} -> "
                f"{mapping_by_surface[surface]!r}"
            )

    if (
        "قَدِيرٌ" in mapping_by_surface
        and "قَادِرٍ" in mapping_by_surface
        and mapping_by_surface["قَدِيرٌ"]
        == mapping_by_surface["قَادِرٍ"]
    ):
        raise RuntimeError(
            "Derivational invariant failed: قَدِيرٌ and قَادِرٍ "
            "must not share one lexical identity."
        )

    if (
        "رَبِّ الْعَالَمِينَ" in mapping_by_surface
        and mapping_by_surface["رَبِّ الْعَالَمِينَ"] == "رَبّ"
    ):
        raise RuntimeError(
            "Multiword invariant failed: رَبِّ الْعَالَمِينَ "
            "must not normalize to standalone رَبّ."
        )

    simple_rabb = [
        "رَبُّكَ",
        "رَبَّكَ",
        "رَبِّكَ",
        "رَبِّي",
        "رَبَّنَا",
    ]
    for surface in simple_rabb:
        if (
            surface in mapping_by_surface
            and mapping_by_surface[surface] != "رَبّ"
        ):
            raise RuntimeError(
                f"Rabb invariant failed: {surface} -> "
                f"{mapping_by_surface[surface]!r}"
            )


def validate_corrections(
    current_map: dict[str, str],
    corrections: Any,
) -> list[dict[str, Any]]:
    findings = []

    if not isinstance(corrections, list):
        return [{"code": "CORRECTIONS_NOT_LIST"}]

    seen = set()

    for i, row in enumerate(corrections):
        if not isinstance(row, dict):
            findings.append({
                "code": "CORRECTION_NOT_OBJECT",
                "index": i,
            })
            continue

        surface = row.get("surface_arabic")
        old = row.get("from_identity")
        new = row.get("to_identity")

        if surface not in current_map:
            findings.append({
                "code": "UNKNOWN_SURFACE",
                "index": i,
                "surface_arabic": surface,
            })
            continue

        if surface in seen:
            findings.append({
                "code": "DUPLICATE_CORRECTION_SURFACE",
                "surface_arabic": surface,
            })
        seen.add(surface)

        if old != current_map[surface]:
            findings.append({
                "code": "FROM_IDENTITY_MISMATCH",
                "surface_arabic": surface,
                "expected": current_map[surface],
                "actual": old,
            })

        if not isinstance(new, str) or not new.strip():
            findings.append({
                "code": "INVALID_TO_IDENTITY",
                "surface_arabic": surface,
                "value": new,
            })
        elif new != new.strip():
            findings.append({
                "code": "TO_IDENTITY_OUTER_WHITESPACE",
                "surface_arabic": surface,
                "value": new,
            })
        elif new == old:
            findings.append({
                "code": "NO_OP_CORRECTION",
                "surface_arabic": surface,
            })

    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "One global GPT-5.6 Sol audit of the complete validated "
            "Phase-2 surface-to-lexeme map, followed by deterministic "
            "application and occurrence joining."
        )
    )
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--confirm-api", action="store_true")
    args = ap.parse_args()

    if not args.confirm_api:
        raise SystemExit(
            "Paid API call blocked. Re-run with --confirm-api."
        )

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    mapping_dir = run_dir / "phase2_surface_mapping_sol_v2"
    clean_prep = run_dir / "phase2_preparation_clean_v1"

    map_path = mapping_dir / "surface_to_lexeme_map.json"
    groups_path = mapping_dir / "lexical_groups.json"
    clean_input_path = (
        clean_prep / "phase2_normalization_v1" / "model_input.json"
    )
    occurrence_path = clean_prep / "phase1_occurrence_ledger.json"
    prompt_path = (
        PROJECT_ROOT
        / "prompts"
        / "phase2_global_mapping_audit_v1.md"
    )
    schema_path = (
        PROJECT_ROOT
        / "schemas"
        / "phase2_global_mapping_audit_v1.schema.json"
    )

    for path in (
        map_path,
        groups_path,
        clean_input_path,
        occurrence_path,
        prompt_path,
        schema_path,
    ):
        if not path.is_file():
            raise SystemExit(f"Missing required file: {path}")

    mapping_doc = read_json(map_path)
    mappings = mapping_doc.get("mappings")
    if not isinstance(mappings, list):
        raise SystemExit("surface_to_lexeme_map.json has no mappings list.")

    clean_input = read_json(clean_input_path)
    candidates = clean_input.get("candidates")
    if not isinstance(candidates, list):
        raise SystemExit("Clean Phase-2 input has no candidates list.")

    clean_surfaces = [x["surface_arabic"] for x in candidates]
    mapped_surfaces = [x["surface_arabic"] for x in mappings]

    if mapped_surfaces != clean_surfaces:
        raise SystemExit(
            "Validated Phase-2 mapping does not exactly match the frozen "
            "clean 446-surface input."
        )

    if len(mappings) != 446:
        raise SystemExit(
            f"Expected 446 mapped surfaces, found {len(mappings)}."
        )

    current_map = {
        row["surface_arabic"]: row["lexical_identity_arabic"]
        for row in mappings
    }

    if len(current_map) != len(mappings):
        raise SystemExit("Duplicate surfaces exist in validated mapping.")

    assert_core_invariants(current_map)

    count_by_surface = {
        x["surface_arabic"]: x["occurrence_count"]
        for x in candidates
    }

    compact_groups = []
    for group in build_groups(mappings):
        compact_groups.append({
            "lexical_identity_arabic": group["lexical_identity_arabic"],
            "members": [
                {
                    "surface_arabic": surface,
                    "occurrence_count": count_by_surface[surface],
                }
                for surface in group["member_surfaces"]
            ],
        })

    audit_input = {
        "surface_count": len(mappings),
        "proposed_identity_count": len(compact_groups),
        "groups": compact_groups,
    }

    out_dir = run_dir / "phase2_global_audit_sol_v1"
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(
            f"Global-audit evidence already exists: {out_dir}\n"
            "Refusing another paid audit call."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = prompt_path.read_text(encoding="utf-8")
    schema = read_json(schema_path)

    request_body = {
        "model": MODEL,
        "reasoning": {"effort": REASONING_EFFORT},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "input": [
            {
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": prompt}
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            audit_input,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": SCHEMA_NAME,
                "strict": True,
                "schema": schema,
            }
        },
    }

    write_json(out_dir / "request_metadata.json", {
        "created_utc": utc_now(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "surface_count": len(mappings),
        "proposed_identity_count": len(compact_groups),
        "sdk_max_retries": 0,
        "automatic_semantic_retries": False,
        "source_map": str(map_path.relative_to(PROJECT_ROOT)),
    })

    write_json(out_dir / "audit_input.json", audit_input)

    load_api_key()

    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("OpenAI Python SDK is not installed.")

    client = OpenAI(max_retries=0)

    print(
        "Calling GPT-5.6 Sol once for the global lexical-mapping audit..."
    )

    try:
        response = client.responses.create(**request_body)
    except Exception as exc:
        write_json(out_dir / "api_error.json", {
            "failed_utc": utc_now(),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "automatic_retry_performed": False,
        })
        print(f"API ERROR: {type(exc).__name__}: {exc}")
        print("No automatic retry was performed.")
        return 2

    raw = plain(response)
    write_json(out_dir / "raw_response.json", raw)

    text = response_output_text(raw)
    if not text:
        write_json(out_dir / "audit_result.json", {
            "status": "NO_OUTPUT_TEXT",
            "corrections": [],
            "validation_findings": [{"code": "NO_OUTPUT_TEXT"}],
            "usage": raw.get("usage"),
        })
        return 3

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        (out_dir / "output_text.txt").write_text(
            text,
            encoding="utf-8",
        )
        write_json(out_dir / "audit_result.json", {
            "status": "PARSE_FAILED",
            "corrections": [],
            "validation_findings": [{
                "code": "JSON_PARSE_FAILED",
                "message": str(exc),
            }],
            "usage": raw.get("usage"),
        })
        return 3

    corrections = parsed.get("corrections")
    findings = validate_corrections(
        current_map,
        corrections,
    )

    if findings:
        write_json(out_dir / "audit_result.json", {
            "status": "VALIDATION_FAILED",
            "corrections": corrections,
            "validation_findings": findings,
            "usage": raw.get("usage"),
        })
        print("Global audit response failed deterministic validation.")
        print(json.dumps(findings, ensure_ascii=False, indent=2))
        return 3

    reviewed_map = copy.deepcopy(current_map)
    for row in corrections:
        reviewed_map[row["surface_arabic"]] = row["to_identity"]

    assert_core_invariants(reviewed_map)

    reviewed_mappings = [
        {
            "surface_arabic": surface,
            "lexical_identity_arabic": reviewed_map[surface],
        }
        for surface in clean_surfaces
    ]

    reviewed_groups = build_groups(reviewed_mappings)

    if len(reviewed_mappings) != 446:
        raise RuntimeError("Reviewed mapping lost surfaces.")

    if set(reviewed_map) != set(clean_surfaces):
        raise RuntimeError("Reviewed mapping changed the surface set.")

    occurrence_doc = read_json(occurrence_path)
    occurrences = occurrence_doc.get("occurrences")
    if not isinstance(occurrences, list):
        raise SystemExit("Clean occurrence ledger has no occurrences list.")

    if len(occurrences) != 5117:
        raise SystemExit(
            f"Expected 5117 clean occurrences, found {len(occurrences)}."
        )

    enriched = []
    lexical_occurrence_counts = Counter()
    lexical_surface_sets = defaultdict(set)

    for occurrence in occurrences:
        surface = occurrence["surface_arabic"]
        if surface not in reviewed_map:
            raise RuntimeError(
                f"Occurrence surface has no reviewed lexical mapping: {surface}"
            )

        row = copy.deepcopy(occurrence)
        identity = reviewed_map[surface]
        row["lexical_identity_arabic"] = identity
        enriched.append(row)
        lexical_occurrence_counts[identity] += 1
        lexical_surface_sets[identity].add(surface)

    lexical_frequency = [
        {
            "lexical_identity_arabic": identity,
            "occurrence_count": lexical_occurrence_counts[identity],
            "exact_surface_count": len(lexical_surface_sets[identity]),
            "member_surfaces": sorted(lexical_surface_sets[identity]),
        }
        for identity in reviewed_map.values()
        if identity in lexical_occurrence_counts
    ]

    seen_identity = set()
    lexical_frequency = [
        row for row in lexical_frequency
        if not (
            row["lexical_identity_arabic"] in seen_identity
            or seen_identity.add(row["lexical_identity_arabic"])
        )
    ]
    lexical_frequency.sort(
        key=lambda x: (
            -x["occurrence_count"],
            x["lexical_identity_arabic"],
        )
    )

    write_json(out_dir / "audit_result.json", {
        "status": "VALIDATED",
        "correction_count": len(corrections),
        "corrections": corrections,
        "validation_findings": [],
        "usage": raw.get("usage"),
    })

    write_json(out_dir / "surface_to_lexeme_map_reviewed.json", {
        "version": "2.1-reviewed",
        "run_name": args.run_name,
        "surface_count": len(reviewed_mappings),
        "lexical_identity_count": len(reviewed_groups),
        "mappings": reviewed_mappings,
    })

    write_json(out_dir / "lexical_groups_reviewed.json", {
        "version": "2.1-reviewed",
        "run_name": args.run_name,
        "surface_count": len(reviewed_mappings),
        "lexical_identity_count": len(reviewed_groups),
        "groups": reviewed_groups,
    })

    write_json(out_dir / "descriptor_occurrences_lexical.json", {
        "version": "2.1-reviewed",
        "run_name": args.run_name,
        "occurrence_count": len(enriched),
        "occurrences": enriched,
    })

    write_json(out_dir / "lexical_frequency.json", {
        "version": "2.1-reviewed",
        "run_name": args.run_name,
        "lexical_identity_count": len(reviewed_groups),
        "total_occurrences": len(enriched),
        "lexical_identities": lexical_frequency,
    })

    usage = raw.get("usage") or {}

    print()
    print("NAMES OF ALLAH — PHASE 2 GLOBAL AUDIT")
    print("=======================================")
    print()
    print("Status: PASS")
    print(f"Mapped exact surfaces: {len(reviewed_mappings)}")
    print(f"Model-proposed corrections: {len(corrections)}")
    print(f"Final lexical identities: {len(reviewed_groups)}")
    print(f"Occurrence records joined: {len(enriched)}")
    print("Automatic retries: 0")
    print(f"Input tokens: {usage.get('input_tokens')}")
    print(f"Output tokens: {usage.get('output_tokens')}")
    print(
        "Reasoning tokens: "
        f"{(usage.get('output_tokens_details') or {}).get('reasoning_tokens')}"
    )
    print(f"Total tokens: {usage.get('total_tokens')}")
    print()
    print(
        "Reviewed map: "
        + str(
            (
                out_dir / "surface_to_lexeme_map_reviewed.json"
            ).relative_to(PROJECT_ROOT)
        )
    )
    print(
        "Reviewed groups: "
        + str(
            (
                out_dir / "lexical_groups_reviewed.json"
            ).relative_to(PROJECT_ROOT)
        )
    )
    print(
        "Occurrence ledger: "
        + str(
            (
                out_dir / "descriptor_occurrences_lexical.json"
            ).relative_to(PROJECT_ROOT)
        )
    )
    print(
        "Frequency: "
        + str(
            (
                out_dir / "lexical_frequency.json"
            ).relative_to(PROJECT_ROOT)
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
