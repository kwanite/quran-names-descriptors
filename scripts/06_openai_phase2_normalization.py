#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
MAX_OUTPUT_TOKENS = 30_000
FULL_MAX_OUTPUT_TOKENS = 80_000
SCHEMA_NAME = "names_of_allah_phase2_lexical_normalization_v1"

PRIVATE_ENV_OVERRIDE_VAR = "NAMES_OF_ALLAH_ENV_FILE"
DEFAULT_PRIVATE_ENV = (
    Path.home() / "Projects" / "PFTT" / "SOURCES" / "quran-roots" / ".env"
)


class WorkflowError(RuntimeError):
    pass


def die(message: str) -> NoReturn:
    raise WorkflowError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"Required file not found: {path}")
    except json.JSONDecodeError as exc:
        die(f"Invalid JSON in {path}: {exc}")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        die(f"Required file not found: {path}")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def plain(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return json.loads(
        json.dumps(obj, default=lambda x: getattr(x, "__dict__", str(x)))
    )


def load_openai_api_key() -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return "process_environment"

    override = os.environ.get(PRIVATE_ENV_OVERRIDE_VAR)
    env_path = (
        Path(override).expanduser()
        if override
        else DEFAULT_PRIVATE_ENV
    )

    if not env_path.is_file():
        die(
            "OPENAI_API_KEY is not set and private .env fallback was not found at: "
            f"{env_path}"
        )

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
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
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not value:
            die(f"OPENAI_API_KEY is empty in {env_path}")
        os.environ["OPENAI_API_KEY"] = value
        return "private_env_file"

    die(f"OPENAI_API_KEY not found in private .env file: {env_path}")


def sdk_client():
    try:
        from openai import OpenAI
    except ImportError:
        die("OpenAI Python SDK is not installed in the active environment.")
    load_openai_api_key()
    return OpenAI(max_retries=0)


def response_output_text(body: dict[str, Any]) -> tuple[str | None, str | None]:
    if isinstance(body.get("output_text"), str) and body["output_text"]:
        return body["output_text"], None

    texts = []
    refusals = []
    for item in body.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
            elif content.get("type") == "refusal" and isinstance(content.get("refusal"), str):
                refusals.append(content["refusal"])

    return (
        "".join(texts) if texts else None,
        "\n".join(refusals) if refusals else None,
    )


def build_body(
    prompt: str,
    schema: dict[str, Any],
    model_input: dict[str, Any],
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    return {
        "model": MODEL,
        "reasoning": {"effort": REASONING_EFFORT},
        "max_output_tokens": max_output_tokens,
        "input": [
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": prompt}],
            },
            {
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": (
                        "Normalize the following complete pilot inventory under "
                        "the developer instructions. Return only the required "
                        "structured output.\n\n"
                        + json.dumps(
                            model_input,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                }],
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


def validate_output(
    model_input: dict[str, Any],
    parsed: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    expected = [
        row["surface_arabic"]
        for row in model_input["candidates"]
    ]
    expected_set = set(expected)

    groups = parsed.get("groups")
    if not isinstance(groups, list):
        return [{"code": "GROUPS_NOT_LIST"}]

    seen = []
    group_for_surface = {}

    for group_index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            findings.append({
                "code": "GROUP_NOT_OBJECT",
                "group_index": group_index,
            })
            continue

        members = group.get("member_surfaces")
        if not isinstance(members, list):
            findings.append({
                "code": "MEMBER_SURFACES_NOT_LIST",
                "group_index": group_index,
            })
            continue

        for member in members:
            seen.append(member)
            group_for_surface.setdefault(member, []).append(group_index)

    seen_counts = Counter(seen)

    missing = [x for x in expected if seen_counts[x] == 0]
    duplicates = sorted(x for x, n in seen_counts.items() if n > 1)
    extras = sorted(x for x in seen_counts if x not in expected_set)

    if missing:
        findings.append({
            "code": "INPUT_SURFACES_MISSING",
            "values": missing,
        })
    if duplicates:
        findings.append({
            "code": "SURFACES_IN_MULTIPLE_GROUPS",
            "values": duplicates,
        })
    if extras:
        findings.append({
            "code": "INVENTED_SURFACES",
            "values": extras,
        })

    # Frozen pilot policy checks.
    allah_surfaces = [
        x for x in ("اللَّهُ", "اللَّهَ", "اللَّهِ", "لِلَّهِ")
        if x in expected_set
    ]
    if allah_surfaces:
        allah_group_indexes = {
            group_for_surface.get(x, [None])[0]
            for x in allah_surfaces
        }
        if len(allah_group_indexes) != 1 or None in allah_group_indexes:
            findings.append({
                "code": "ALLAH_VARIANTS_NOT_GROUPED_TOGETHER",
                "values": allah_surfaces,
            })
        else:
            idx = next(iter(allah_group_indexes))
            if idx is not None:
                g = groups[idx - 1]
                if g.get("lexical_identity_arabic") != "اللَّه":
                    findings.append({
                        "code": "ALLAH_LEXICAL_IDENTITY_MISMATCH",
                        "value": g.get("lexical_identity_arabic"),
                    })
                if g.get("linguistic_class") != "proper_name":
                    findings.append({
                        "code": "ALLAH_NOT_CLASSIFIED_AS_PROPER_NAME",
                        "value": g.get("linguistic_class"),
                    })

    simple_rabb = [
        x for x in (
            "رَبُّكَ", "رَبَّكَ", "رَبِّكَ",
            "رَبِّي", "رَبَّنَا"
        )
        if x in expected_set
    ]
    if len(simple_rabb) >= 2:
        rabb_indexes = {
            group_for_surface.get(x, [None])[0]
            for x in simple_rabb
        }
        if len(rabb_indexes) != 1 or None in rabb_indexes:
            findings.append({
                "code": "SIMPLE_RABB_VARIANTS_NOT_GROUPED_TOGETHER",
                "values": simple_rabb,
            })
        else:
            idx = next(iter(rabb_indexes))
            if idx is not None:
                g = groups[idx - 1]
                if g.get("lexical_identity_arabic") != "رَبّ":
                    findings.append({
                        "code": "RABB_LEXICAL_IDENTITY_MISMATCH",
                        "value": g.get("lexical_identity_arabic"),
                    })

    if (
        "رَبِّ الْعَالَمِينَ" in expected_set
        and simple_rabb
    ):
        multi_idx = group_for_surface.get("رَبِّ الْعَالَمِينَ", [None])[0]
        simple_idx = group_for_surface.get(simple_rabb[0], [None])[0]
        if multi_idx is not None and multi_idx == simple_idx:
            findings.append({
                "code": "RABB_AL_ALAMIN_COLLAPSED_TO_SIMPLE_RABB",
            })

    if "قَدِيرٌ" in expected_set and "قَادِرٍ" in expected_set:
        qadir1 = group_for_surface.get("قَدِيرٌ", [None])[0]
        qadir2 = group_for_surface.get("قَادِرٍ", [None])[0]
        if qadir1 is not None and qadir1 == qadir2:
            findings.append({
                "code": "DERIVATIONALLY_DISTINCT_QADIR_FORMS_MERGED",
            })

    return findings


def pilot_sync(args) -> int:
    if not args.confirm_api:
        die(
            "Paid API call blocked. Re-run with --confirm-api after reviewing "
            "the prepared pilot input."
        )

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    prep_dir = (
        run_dir
        / "phase2_preparation"
        / "phase2_normalization_v1"
    )
    pilot_input_path = prep_dir / "pilot_model_input.json"
    prompt_path = PROJECT_ROOT / "prompts" / "phase2_lexical_normalization_v1.md"
    schema_path = PROJECT_ROOT / "schemas" / "phase2_lexical_normalization_v1.schema.json"

    for path in (pilot_input_path, prompt_path, schema_path):
        if not path.is_file():
            die(f"Required file not found: {path}")

    evidence_dir = prep_dir / "pilot_sync_v1"
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        die(
            f"Pilot evidence already exists at {evidence_dir}\n"
            "Refusing to make another paid request. Inspect existing evidence."
        )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    model_input = read_json(pilot_input_path)
    prompt = read_text(prompt_path)
    schema = read_json(schema_path)

    body = build_body(prompt, schema, model_input, MAX_OUTPUT_TOKENS)

    request_record = {
        "created_utc": utc_now(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "automatic_sdk_retries": 0,
        "automatic_semantic_retries": False,
        "prompt_sha256": sha256_file(prompt_path),
        "schema_sha256": sha256_file(schema_path),
        "pilot_input_sha256": sha256_file(pilot_input_path),
        "surface_count": model_input["surface_count"],
    }
    atomic_write_json(evidence_dir / "request_metadata.json", request_record)

    print("Calling OpenAI Responses API for the 15-surface Phase 2 pilot...")
    started = utc_now()

    try:
        response = sdk_client().responses.create(**body)
    except Exception as exc:
        atomic_write_json(evidence_dir / "api_error.json", {
            "started_utc": started,
            "failed_utc": utc_now(),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "automatic_retry_performed": False,
        })
        print(f"API ERROR: {type(exc).__name__}: {exc}")
        print("No automatic retry was performed.")
        return 2

    raw = plain(response)
    atomic_write_json(evidence_dir / "raw_response.json", raw)

    output_text, refusal = response_output_text(raw)
    result = {
        "request_started_utc": started,
        "response_saved_utc": utc_now(),
        "response_id": raw.get("id"),
        "response_status": raw.get("status"),
        "usage": raw.get("usage"),
        "refusal": refusal,
        "raw_response_file": "raw_response.json",
        "model_parsed_output": None,
        "validation_findings": [],
        "collection_status": None,
    }

    if refusal:
        result["collection_status"] = "REFUSED"
    elif not output_text:
        result["collection_status"] = "NO_OUTPUT_TEXT"
        result["validation_findings"] = [{"code": "NO_OUTPUT_TEXT"}]
    else:
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            result["collection_status"] = "PARSE_FAILED"
            result["validation_findings"] = [{
                "code": "JSON_PARSE_FAILED",
                "message": str(exc),
            }]
            atomic_write_text(evidence_dir / "output_text.txt", output_text)
        else:
            result["model_parsed_output"] = parsed
            findings = validate_output(model_input, parsed)
            result["validation_findings"] = findings
            result["collection_status"] = (
                "VALIDATED"
                if not findings
                else "VALIDATION_FAILED"
            )

    atomic_write_json(evidence_dir / "pilot_result.json", result)

    usage = result.get("usage") or {}
    groups = (
        len(result["model_parsed_output"].get("groups", []))
        if isinstance(result.get("model_parsed_output"), dict)
        else 0
    )

    print()
    print("NAMES OF ALLAH — PHASE 2 NORMALIZATION PILOT")
    print("================================================")
    print()
    print(f"Status: {result['collection_status']}")
    print(f"Input surfaces: {model_input['surface_count']}")
    print(f"Output groups: {groups}")
    print(f"Validation findings: {len(result['validation_findings'])}")
    print(f"Input tokens: {usage.get('input_tokens')}")
    print(f"Output tokens: {usage.get('output_tokens')}")
    print(f"Reasoning tokens: {(usage.get('output_tokens_details') or {}).get('reasoning_tokens')}")
    print(f"Total tokens: {usage.get('total_tokens')}")
    print()
    print(f"Evidence: {evidence_dir.relative_to(PROJECT_ROOT)}")
    print("No automatic retry was performed.")

    if result["validation_findings"]:
        print()
        print(json.dumps(
            result["validation_findings"],
            ensure_ascii=False,
            indent=2,
        ))
        return 3

    return 0



def full_sync(args) -> int:
    if not args.confirm_api:
        die(
            "Paid API call blocked. Re-run with --confirm-api after reviewing "
            "the prepared 450-surface input."
        )

    run_dir = PROJECT_ROOT / "runs" / args.run_name
    prep_dir = (
        run_dir
        / "phase2_preparation"
        / "phase2_normalization_v1"
    )
    model_input_path = prep_dir / "model_input.json"
    prompt_path = PROJECT_ROOT / "prompts" / "phase2_lexical_normalization_v1.md"
    schema_path = PROJECT_ROOT / "schemas" / "phase2_lexical_normalization_v1.schema.json"

    for path in (model_input_path, prompt_path, schema_path):
        if not path.is_file():
            die(f"Required file not found: {path}")

    evidence_dir = prep_dir / "full_sync_v1"
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        die(
            f"Full-run evidence already exists at {evidence_dir}\n"
            "Refusing to make another paid request. Inspect existing evidence."
        )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    model_input = read_json(model_input_path)
    prompt = read_text(prompt_path)
    schema = read_json(schema_path)

    if model_input.get("surface_count") != 450:
        die(
            f"Expected 450 surfaces in prepared full input, found "
            f"{model_input.get('surface_count')}"
        )

    body = build_body(
        prompt,
        schema,
        model_input,
        FULL_MAX_OUTPUT_TOKENS,
    )

    request_record = {
        "created_utc": utc_now(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "max_output_tokens": FULL_MAX_OUTPUT_TOKENS,
        "automatic_sdk_retries": 0,
        "automatic_semantic_retries": False,
        "prompt_sha256": sha256_file(prompt_path),
        "schema_sha256": sha256_file(schema_path),
        "model_input_sha256": sha256_file(model_input_path),
        "surface_count": model_input["surface_count"],
    }
    atomic_write_json(evidence_dir / "request_metadata.json", request_record)

    print("Calling OpenAI Responses API for the full 450-surface Phase 2 normalization...")
    started = utc_now()

    try:
        response = sdk_client().responses.create(**body)
    except Exception as exc:
        atomic_write_json(evidence_dir / "api_error.json", {
            "started_utc": started,
            "failed_utc": utc_now(),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "automatic_retry_performed": False,
        })
        print(f"API ERROR: {type(exc).__name__}: {exc}")
        print("No automatic retry was performed.")
        return 2

    raw = plain(response)
    atomic_write_json(evidence_dir / "raw_response.json", raw)

    output_text, refusal = response_output_text(raw)
    result = {
        "request_started_utc": started,
        "response_saved_utc": utc_now(),
        "response_id": raw.get("id"),
        "response_status": raw.get("status"),
        "usage": raw.get("usage"),
        "refusal": refusal,
        "raw_response_file": "raw_response.json",
        "model_parsed_output": None,
        "validation_findings": [],
        "collection_status": None,
    }

    if refusal:
        result["collection_status"] = "REFUSED"
    elif not output_text:
        result["collection_status"] = "NO_OUTPUT_TEXT"
        result["validation_findings"] = [{"code": "NO_OUTPUT_TEXT"}]
    else:
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            result["collection_status"] = "PARSE_FAILED"
            result["validation_findings"] = [{
                "code": "JSON_PARSE_FAILED",
                "message": str(exc),
            }]
            atomic_write_text(evidence_dir / "output_text.txt", output_text)
        else:
            result["model_parsed_output"] = parsed
            findings = validate_output(model_input, parsed)
            result["validation_findings"] = findings
            result["collection_status"] = (
                "VALIDATED"
                if not findings
                else "VALIDATION_FAILED"
            )

    atomic_write_json(evidence_dir / "full_result.json", result)

    usage = result.get("usage") or {}
    groups = (
        len(result["model_parsed_output"].get("groups", []))
        if isinstance(result.get("model_parsed_output"), dict)
        else 0
    )

    print()
    print("NAMES OF ALLAH — PHASE 2 FULL NORMALIZATION")
    print("===============================================")
    print()
    print(f"Status: {result['collection_status']}")
    print(f"Input surfaces: {model_input['surface_count']}")
    print(f"Output groups: {groups}")
    print(f"Validation findings: {len(result['validation_findings'])}")
    print(f"Input tokens: {usage.get('input_tokens')}")
    print(f"Output tokens: {usage.get('output_tokens')}")
    print(f"Reasoning tokens: {(usage.get('output_tokens_details') or {}).get('reasoning_tokens')}")
    print(f"Total tokens: {usage.get('total_tokens')}")
    print()
    print(f"Evidence: {evidence_dir.relative_to(PROJECT_ROOT)}")
    print("No automatic retry was performed.")

    if result["validation_findings"]:
        print()
        print(json.dumps(
            result["validation_findings"],
            ensure_ascii=False,
            indent=2,
        ))
        return 3

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pilot-sync")
    p.add_argument("--run-name", required=True)
    p.add_argument("--confirm-api", action="store_true")

    f = sub.add_parser("full-sync")
    f.add_argument("--run-name", required=True)
    f.add_argument("--confirm-api", action="store_true")

    args = ap.parse_args()

    try:
        if args.command == "pilot-sync":
            return pilot_sync(args)
        if args.command == "full-sync":
            return full_sync(args)
        die(f"Unknown command: {args.command}")
    except WorkflowError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
