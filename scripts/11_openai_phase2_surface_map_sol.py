#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "high"
BATCH_SIZE = 20
MAX_OUTPUT_TOKENS = 8_000
SCHEMA_NAME = "names_of_allah_surface_to_identity_v2"

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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


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


def validate_batch(
    candidates: list[dict[str, Any]],
    parsed: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    mappings = parsed.get("mappings")
    if not isinstance(mappings, list):
        return [{"code": "MAPPINGS_NOT_LIST"}]

    expected = [x["surface_arabic"] for x in candidates]
    returned = [
        x.get("surface_arabic")
        for x in mappings
        if isinstance(x, dict)
    ]

    if len(mappings) != len(candidates):
        findings.append({
            "code": "MAPPING_COUNT_MISMATCH",
            "expected": len(candidates),
            "actual": len(mappings),
        })

    if returned != expected:
        findings.append({
            "code": "SURFACE_SEQUENCE_MISMATCH",
            "expected": expected,
            "actual": returned,
        })

    counts = Counter(returned)
    duplicates = sorted(
        x for x, n in counts.items()
        if isinstance(x, str) and n > 1
    )
    if duplicates:
        findings.append({
            "code": "SURFACE_DUPLICATED",
            "values": duplicates,
        })

    expected_set = set(expected)
    invented = sorted(
        x for x in counts
        if isinstance(x, str) and x not in expected_set
    )
    if invented:
        findings.append({
            "code": "SURFACE_INVENTED",
            "values": invented,
        })

    for i, row in enumerate(mappings):
        if not isinstance(row, dict):
            findings.append({
                "code": "MAPPING_NOT_OBJECT",
                "index": i,
            })
            continue

        identity = row.get("lexical_identity_arabic")
        if not isinstance(identity, str) or not identity.strip():
            findings.append({
                "code": "INVALID_LEXICAL_IDENTITY",
                "index": i,
                "value": identity,
            })
        elif identity != identity.strip():
            findings.append({
                "code": "LEXICAL_IDENTITY_OUTER_WHITESPACE",
                "index": i,
                "value": identity,
            })

    return findings


def build_existing_identities(
    accepted_mappings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    groups: OrderedDict[str, list[str]] = OrderedDict()

    for row in accepted_mappings:
        identity = row["lexical_identity_arabic"]
        surface = row["surface_arabic"]
        groups.setdefault(identity, [])
        if surface not in groups[identity]:
            groups[identity].append(surface)

    return [
        {
            "lexical_identity_arabic": identity,
            "member_surfaces": members[:5],
        }
        for identity, members in groups.items()
    ]


def batch_chunks(
    candidates: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    return [
        candidates[i:i + BATCH_SIZE]
        for i in range(0, len(candidates), BATCH_SIZE)
    ]


def load_validated_batch(
    batch_dir: Path,
    expected_surfaces: list[str],
) -> list[dict[str, str]] | None:
    result_path = batch_dir / "batch_result.json"
    if not result_path.is_file():
        return None

    result = read_json(result_path)
    if result.get("status") != "VALIDATED":
        return None

    mappings = result.get("mappings")
    if not isinstance(mappings, list):
        return None

    actual_surfaces = [x.get("surface_arabic") for x in mappings]
    if actual_surfaces != expected_surfaces:
        raise RuntimeError(
            f"Existing validated batch no longer matches current input: "
            f"{batch_dir}"
        )

    return mappings


def save_failed_batch_dir(
    canonical_batch_dir: Path,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    failed = canonical_batch_dir.with_name(
        canonical_batch_dir.name + f"_failed_{stamp}"
    )
    if failed.exists():
        raise RuntimeError(f"Failed evidence path already exists: {failed}")
    os.replace(canonical_batch_dir, failed)
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Phase 2 v2: map each exact Quran surface to one lexical identity "
            "using small validated GPT-5.6 Sol batches."
        )
    )
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--confirm-api", action="store_true")
    args = ap.parse_args()

    if not args.confirm_api:
        raise SystemExit(
            "Paid API calls blocked. Re-run with --confirm-api."
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
        / "phase2_surface_to_identity_v2.md"
    )
    schema_path = (
        PROJECT_ROOT
        / "schemas"
        / "phase2_surface_to_identity_v2.schema.json"
    )

    for path in (input_path, prompt_path, schema_path):
        if not path.is_file():
            raise SystemExit(f"Missing required file: {path}")

    model_input = read_json(input_path)
    candidates = model_input.get("candidates")

    if not isinstance(candidates, list):
        raise SystemExit("Clean Phase-2 input has no candidates list.")

    if model_input.get("surface_count") != len(candidates):
        raise SystemExit(
            "surface_count does not match candidates length."
        )

    all_surfaces = [x["surface_arabic"] for x in candidates]
    if len(all_surfaces) != len(set(all_surfaces)):
        raise SystemExit(
            "Clean Phase-2 input contains duplicate exact surfaces."
        )

    if len(candidates) != 446:
        raise SystemExit(
            f"Expected the frozen clean inventory of 446 surfaces; "
            f"found {len(candidates)}."
        )

    prompt = prompt_path.read_text(encoding="utf-8")
    schema = read_json(schema_path)

    out_dir = run_dir / "phase2_surface_mapping_sol_v2"
    batches_dir = out_dir / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)

    chunks = batch_chunks(candidates)
    accepted: list[dict[str, str]] = []
    api_calls_this_run = 0
    resumed_batches = 0

    load_api_key()

    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("OpenAI Python SDK is not installed.")

    client = OpenAI(max_retries=0)

    print("NAMES OF ALLAH — PHASE 2 SURFACE MAPPING V2")
    print("=============================================")
    print()
    print(f"Model: {MODEL}")
    print(f"Reasoning: {REASONING_EFFORT}")
    print(f"Exact input surfaces: {len(candidates)}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Total batches: {len(chunks)}")
    print()

    for batch_index, chunk in enumerate(chunks, 1):
        batch_name = f"batch_{batch_index:03d}"
        batch_dir = batches_dir / batch_name
        expected_surfaces = [x["surface_arabic"] for x in chunk]

        if batch_dir.exists():
            validated = load_validated_batch(
                batch_dir,
                expected_surfaces,
            )
            if validated is not None:
                accepted.extend(validated)
                resumed_batches += 1
                print(
                    f"{batch_name}: VALIDATED (existing evidence; resumed)"
                )
                continue

            raise SystemExit(
                f"Existing non-validated canonical batch directory found: "
                f"{batch_dir}\n"
                "Inspect it before continuing."
            )

        batch_dir.mkdir(parents=True)

        existing_identities = build_existing_identities(accepted)

        request_payload = {
            "batch_number": batch_index,
            "batch_count": len(chunks),
            "candidate_count": len(chunk),
            "existing_identity_count": len(existing_identities),
            "existing_identities": existing_identities,
            "candidates": chunk,
        }

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
                            "text": json.dumps(
                                request_payload,
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

        write_json(batch_dir / "request_metadata.json", {
            "created_utc": utc_now(),
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "batch_number": batch_index,
            "batch_count": len(chunks),
            "candidate_count": len(chunk),
            "candidate_surfaces": expected_surfaces,
            "existing_identity_count": len(existing_identities),
            "input_sha256": sha256_file(input_path),
            "prompt_sha256": sha256_file(prompt_path),
            "schema_sha256": sha256_file(schema_path),
            "sdk_max_retries": 0,
            "automatic_semantic_retries": False,
        })

        print(
            f"{batch_name}: calling API for {len(chunk)} surfaces "
            f"with {len(existing_identities)} established identities..."
        )

        try:
            response = client.responses.create(**request_body)
        except Exception as exc:
            write_json(batch_dir / "api_error.json", {
                "failed_utc": utc_now(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "automatic_retry_performed": False,
            })
            failed_dir = save_failed_batch_dir(batch_dir)
            print(
                f"{batch_name}: API ERROR; evidence preserved at "
                f"{failed_dir.relative_to(PROJECT_ROOT)}"
            )
            print("No automatic retry was performed.")
            return 2

        api_calls_this_run += 1
        raw = plain(response)
        write_json(batch_dir / "raw_response.json", raw)

        text = response_output_text(raw)
        if not text:
            write_json(batch_dir / "batch_result.json", {
                "status": "NO_OUTPUT_TEXT",
                "mappings": [],
                "validation_findings": [{"code": "NO_OUTPUT_TEXT"}],
                "usage": raw.get("usage"),
            })
            failed_dir = save_failed_batch_dir(batch_dir)
            print(
                f"{batch_name}: NO_OUTPUT_TEXT; evidence preserved at "
                f"{failed_dir.relative_to(PROJECT_ROOT)}"
            )
            return 3

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            (batch_dir / "output_text.txt").write_text(
                text,
                encoding="utf-8",
            )
            write_json(batch_dir / "batch_result.json", {
                "status": "PARSE_FAILED",
                "mappings": [],
                "validation_findings": [{
                    "code": "JSON_PARSE_FAILED",
                    "message": str(exc),
                }],
                "usage": raw.get("usage"),
            })
            failed_dir = save_failed_batch_dir(batch_dir)
            print(
                f"{batch_name}: PARSE_FAILED; evidence preserved at "
                f"{failed_dir.relative_to(PROJECT_ROOT)}"
            )
            return 3

        findings = validate_batch(chunk, parsed)
        mappings = parsed.get("mappings", [])

        write_json(batch_dir / "batch_result.json", {
            "status": "VALIDATED" if not findings else "VALIDATION_FAILED",
            "mappings": mappings,
            "validation_findings": findings,
            "usage": raw.get("usage"),
        })

        if findings:
            failed_dir = save_failed_batch_dir(batch_dir)
            print(
                f"{batch_name}: VALIDATION_FAILED; evidence preserved at "
                f"{failed_dir.relative_to(PROJECT_ROOT)}"
            )
            print(json.dumps(
                findings,
                ensure_ascii=False,
                indent=2,
            ))
            return 3

        accepted.extend(mappings)
        print(
            f"{batch_name}: VALIDATED — "
            f"{len(accepted)}/{len(candidates)} surfaces mapped"
        )

    if len(accepted) != len(candidates):
        raise SystemExit(
            f"Final mapping count mismatch: {len(accepted)} vs "
            f"{len(candidates)}"
        )

    accepted_surfaces = [x["surface_arabic"] for x in accepted]
    if accepted_surfaces != all_surfaces:
        raise SystemExit(
            "Final surface sequence does not exactly match clean input."
        )

    groups: OrderedDict[str, list[str]] = OrderedDict()
    for row in accepted:
        groups.setdefault(row["lexical_identity_arabic"], [])
        groups[row["lexical_identity_arabic"]].append(
            row["surface_arabic"]
        )

    grouped_output = [
        {
            "lexical_identity_arabic": identity,
            "member_surfaces": members,
        }
        for identity, members in groups.items()
    ]

    write_json(out_dir / "surface_to_lexeme_map.json", {
        "version": "2.0",
        "run_name": args.run_name,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "source_input": str(input_path.relative_to(PROJECT_ROOT)),
        "surface_count": len(accepted),
        "mappings": accepted,
    })

    write_json(out_dir / "lexical_groups.json", {
        "version": "2.0",
        "run_name": args.run_name,
        "surface_count": len(accepted),
        "lexical_identity_count": len(grouped_output),
        "groups": grouped_output,
    })

    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }

    for batch_index in range(1, len(chunks) + 1):
        result = read_json(
            batches_dir
            / f"batch_{batch_index:03d}"
            / "batch_result.json"
        )
        usage = result.get("usage") or {}
        total_usage["input_tokens"] += usage.get("input_tokens") or 0
        total_usage["output_tokens"] += usage.get("output_tokens") or 0
        total_usage["total_tokens"] += usage.get("total_tokens") or 0
        details = usage.get("output_tokens_details") or {}
        total_usage["reasoning_tokens"] += (
            details.get("reasoning_tokens") or 0
        )

    report = {
        "status": "PASS",
        "run_name": args.run_name,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "batch_size": BATCH_SIZE,
        "batch_count": len(chunks),
        "surface_count": len(accepted),
        "lexical_identity_count": len(grouped_output),
        "api_calls_this_run": api_calls_this_run,
        "resumed_validated_batches": resumed_batches,
        "automatic_retries": 0,
        "total_usage": total_usage,
        "outputs": {
            "surface_to_lexeme_map": str(
                (
                    out_dir / "surface_to_lexeme_map.json"
                ).relative_to(PROJECT_ROOT)
            ),
            "lexical_groups": str(
                (
                    out_dir / "lexical_groups.json"
                ).relative_to(PROJECT_ROOT)
            ),
        },
    }

    write_json(out_dir / "phase2_mapping_report.json", report)

    print()
    print("PHASE 2 SURFACE MAPPING COMPLETE")
    print("================================")
    print()
    print("Status: PASS")
    print(f"Exact surfaces mapped: {len(accepted)}")
    print(f"Lexical identities produced: {len(grouped_output)}")
    print(f"Validated batches: {len(chunks)}")
    print(f"API calls this run: {api_calls_this_run}")
    print(f"Resumed validated batches: {resumed_batches}")
    print("Automatic retries: 0")
    print(f"Input tokens: {total_usage['input_tokens']}")
    print(f"Output tokens: {total_usage['output_tokens']}")
    print(f"Reasoning tokens: {total_usage['reasoning_tokens']}")
    print(f"Total tokens: {total_usage['total_tokens']}")
    print()
    print(
        "Map: "
        + str(
            (
                out_dir / "surface_to_lexeme_map.json"
            ).relative_to(PROJECT_ROOT)
        )
    )
    print(
        "Groups: "
        + str(
            (
                out_dir / "lexical_groups.json"
            ).relative_to(PROJECT_ROOT)
        )
    )
    print(
        "Report: "
        + str(
            (
                out_dir / "phase2_mapping_report.json"
            ).relative_to(PROJECT_ROOT)
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
