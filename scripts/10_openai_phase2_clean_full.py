#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
MAX_OUTPUT_TOKENS = 80_000
SCHEMA_NAME = "names_of_allah_phase2_lexical_normalization_v1"

PRIVATE_ENV_OVERRIDE_VAR = "NAMES_OF_ALLAH_ENV_FILE"
DEFAULT_PRIVATE_ENV = (
    Path.home() / "Projects" / "PFTT" / "SOURCES" / "quran-roots" / ".env"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
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
            f"OPENAI_API_KEY is not set and private .env was not found: {env_path}"
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


def output_text(raw: dict[str, Any]) -> str | None:
    if isinstance(raw.get("output_text"), str) and raw["output_text"]:
        return raw["output_text"]

    pieces = []
    for item in raw.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    pieces.append(text)

    return "".join(pieces) if pieces else None


def validate_exact_coverage(
    model_input: dict[str, Any],
    parsed: dict[str, Any],
) -> list[dict[str, Any]]:
    findings = []

    expected = [
        row["surface_arabic"]
        for row in model_input["candidates"]
    ]
    expected_set = set(expected)

    groups = parsed.get("groups")
    if not isinstance(groups, list):
        return [{"code": "GROUPS_NOT_LIST"}]

    returned = []
    for i, group in enumerate(groups, 1):
        if not isinstance(group, dict):
            findings.append({
                "code": "GROUP_NOT_OBJECT",
                "group_index": i,
            })
            continue

        members = group.get("member_surfaces")
        if not isinstance(members, list):
            findings.append({
                "code": "MEMBER_SURFACES_NOT_LIST",
                "group_index": i,
            })
            continue

        returned.extend(members)

    counts = Counter(returned)

    missing = [x for x in expected if counts[x] == 0]
    duplicates = sorted(x for x, n in counts.items() if n > 1)
    invented = sorted(x for x in counts if x not in expected_set)

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

    if invented:
        findings.append({
            "code": "INVENTED_SURFACES",
            "values": invented,
        })

    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--confirm-api", action="store_true")
    args = ap.parse_args()

    if not args.confirm_api:
        raise SystemExit(
            "Paid API call blocked. Re-run with --confirm-api."
        )

    run_dir = PROJECT_ROOT / "runs" / args.run_name

    input_path = (
        run_dir
        / "phase2_preparation_clean_v1"
        / "phase2_normalization_v1"
        / "model_input.json"
    )
    prompt_path = (
        PROJECT_ROOT
        / "prompts"
        / "phase2_lexical_normalization_v1.md"
    )
    schema_path = (
        PROJECT_ROOT
        / "schemas"
        / "phase2_lexical_normalization_v1.schema.json"
    )

    for path in (input_path, prompt_path, schema_path):
        if not path.is_file():
            raise SystemExit(f"Missing required file: {path}")

    model_input = load_json(input_path)
    candidates = model_input.get("candidates")

    if not isinstance(candidates, list):
        raise SystemExit("Clean Phase-2 input has no candidates list.")

    if model_input.get("surface_count") != len(candidates):
        raise SystemExit(
            "Clean Phase-2 input surface_count does not match candidates length."
        )

    surfaces = [x["surface_arabic"] for x in candidates]
    if len(surfaces) != len(set(surfaces)):
        raise SystemExit("Clean Phase-2 input contains duplicate surface entries.")

    evidence_dir = (
        run_dir
        / "phase2_clean_full_sync_v1"
    )

    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise SystemExit(
            f"Refusing another paid request because evidence already exists: "
            f"{evidence_dir}"
        )

    evidence_dir.mkdir(parents=True, exist_ok=True)

    prompt = prompt_path.read_text(encoding="utf-8")
    schema = load_json(schema_path)

    request_body = {
        "model": MODEL,
        "reasoning": {"effort": REASONING_EFFORT},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "input": [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Normalize the following complete clean inventory "
                            "under the developer instructions. Return only the "
                            "required structured output.\n\n"
                            + json.dumps(
                                model_input,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
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

    save_json(evidence_dir / "request_metadata.json", {
        "created_utc": utc_now(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "surface_count": len(candidates),
        "sdk_retries": 0,
        "semantic_retries": False,
        "source_input": str(input_path.relative_to(PROJECT_ROOT)),
    })

    load_api_key()

    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("OpenAI Python SDK is not installed.")

    client = OpenAI(max_retries=0)

    print(
        f"Calling OpenAI Responses API for the clean "
        f"{len(candidates)}-surface Phase 2 normalization..."
    )

    try:
        response = client.responses.create(**request_body)
    except Exception as exc:
        save_json(evidence_dir / "api_error.json", {
            "failed_utc": utc_now(),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "automatic_retry_performed": False,
        })
        print(f"API ERROR: {type(exc).__name__}: {exc}")
        print("No automatic retry was performed.")
        return 2

    raw = plain(response)
    save_json(evidence_dir / "raw_response.json", raw)

    text = output_text(raw)

    result = {
        "response_id": raw.get("id"),
        "response_status": raw.get("status"),
        "usage": raw.get("usage"),
        "surface_count": len(candidates),
        "model_parsed_output": None,
        "validation_findings": [],
        "status": None,
    }

    if not text:
        result["status"] = "NO_OUTPUT_TEXT"
        result["validation_findings"] = [{"code": "NO_OUTPUT_TEXT"}]
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            (evidence_dir / "output_text.txt").write_text(
                text,
                encoding="utf-8",
            )
            result["status"] = "PARSE_FAILED"
            result["validation_findings"] = [{
                "code": "JSON_PARSE_FAILED",
                "message": str(exc),
            }]
        else:
            result["model_parsed_output"] = parsed
            findings = validate_exact_coverage(
                model_input,
                parsed,
            )
            result["validation_findings"] = findings
            result["status"] = (
                "VALIDATED"
                if not findings
                else "VALIDATION_FAILED"
            )

    save_json(evidence_dir / "phase2_result.json", result)

    usage = result.get("usage") or {}
    groups = (
        len(result["model_parsed_output"].get("groups", []))
        if isinstance(result.get("model_parsed_output"), dict)
        else 0
    )

    print()
    print("NAMES OF ALLAH — PHASE 2 CLEAN FULL NORMALIZATION")
    print("===================================================")
    print()
    print(f"Status: {result['status']}")
    print(f"Input surfaces: {len(candidates)}")
    print(f"Output groups: {groups}")
    print(
        f"Validation findings: "
        f"{len(result['validation_findings'])}"
    )
    print(f"Input tokens: {usage.get('input_tokens')}")
    print(f"Output tokens: {usage.get('output_tokens')}")
    print(
        "Reasoning tokens: "
        f"{(usage.get('output_tokens_details') or {}).get('reasoning_tokens')}"
    )
    print(f"Total tokens: {usage.get('total_tokens')}")
    print()
    print(
        "Evidence: "
        + str(evidence_dir.relative_to(PROJECT_ROOT))
    )
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


if __name__ == "__main__":
    raise SystemExit(main())
