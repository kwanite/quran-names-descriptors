#!/usr/bin/env python3
"""
02_openai_batch_allah_names_phase1.py

Phase 1 OpenAI manager for simplified Quran-only Allah descriptor extraction.

Commands:
  prepare     - local only; NO API CALL
  pilot-sync  - run the frozen six-request pilot synchronously
  submit      - submit the full/selected run through OpenAI Batch
  status      - retrieve existing Batch status
  collect     - download raw Batch outputs/errors, then structurally validate

The long extraction prompt is sent as a developer-role input message rather
than the Responses API `instructions` field. This avoids the current short
`instructions` length limit and preserves instruction hierarchy.

No automatic paid retry/resubmission is performed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import os
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

SCRIPT_VERSION = "3.2.5"
TASK_ID = "names-of-allah-phase1-descriptor-extraction-v3"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
MAX_OUTPUT_TOKENS = 80_000
BATCH_ENDPOINT = "/v1/responses"
COMPLETION_WINDOW = "24h"
SCHEMA_NAME = "names_of_allah_phase1_descriptor_extraction_v3"
PROMPT_REL = "prompts/phase1_descriptor_extraction_v3_2.md"
SCHEMA_REL = "schemas/phase1_descriptor_output_v3.schema.json"
MAX_BATCH_FILE_BYTES = 200 * 1024 * 1024

PILOT_PACKET_IDS = [
    "allah-names-v1-s001-c01-a001-007",
    "allah-names-v1-s002-c01-a001-050",
    "allah-names-v1-s038-c01-a001-050",
    "allah-names-v1-s059-c01-a001-024",
    "allah-names-v1-s075-c01-a001-040",
    "allah-names-v1-s112-c01-a001-004",
]

TERMINAL_BATCH_STATUSES = {"completed", "failed", "expired", "cancelled"}


class WorkflowError(RuntimeError):
    pass


def die(message: str) -> NoReturn:
    raise WorkflowError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        die(f"Required file not found: {path}")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"Required file not found: {path}")
    except json.JSONDecodeError as exc:
        die(f"Invalid JSON in {path}: {exc}")


def ensure_fresh_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        die(
            f"Run directory already exists and is non-empty: {path}\n"
            "Use a new --run-name. Prior evidence will not be overwritten."
        )
    path.mkdir(parents=True, exist_ok=True)


PRIVATE_ENV_OVERRIDE_VAR = "NAMES_OF_ALLAH_ENV_FILE"
DEFAULT_PRIVATE_ENV = (
    Path.home() / "Projects" / "PFTT" / "SOURCES" / "quran-roots" / ".env"
)


def load_openai_api_key() -> str:
    """
    Ensure OPENAI_API_KEY is available without copying secrets into this repo.

    Precedence:
    1. Existing OPENAI_API_KEY in the process environment.
    2. NAMES_OF_ALLAH_ENV_FILE, if set.
    3. ~/Projects/PFTT/SOURCES/quran-roots/.env

    Returns only a non-secret source label. Never logs the key or .env contents.
    """
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
            "OPENAI_API_KEY is not set, and the private .env fallback was not "
            f"found at: {env_path}\\n"
            f"Set OPENAI_API_KEY or set {PRIVATE_ENV_OVERRIDE_VAR} to another "
            "private .env file."
        )

    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        die(f"Could not read private .env file {env_path}: {exc}")

    for raw_line in lines:
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
            die(f"OPENAI_API_KEY is present but empty in {env_path}.")

        os.environ["OPENAI_API_KEY"] = value
        return "private_env_file"

    die(f"OPENAI_API_KEY was not found in private .env file: {env_path}")


def sdk_client():
    try:
        from openai import OpenAI
    except ImportError:
        die("OpenAI Python SDK is not installed.")

    load_openai_api_key()
    return OpenAI(max_retries=0)


def plain(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return json.loads(
        json.dumps(obj, default=lambda x: getattr(x, "__dict__", str(x)))
    )


def load_preprocessing(repo_root: Path):
    pre = repo_root / "runs" / "preprocessing_v1"
    report = read_json(pre / "preprocessing_report.json")
    manifest = read_json(pre / "packet_manifest.json")

    if report.get("status") != "PASS":
        die("runs/preprocessing_v1 is not PASS.")
    if report.get("canonical_verse_count") != 6236:
        die("Expected 6,236 canonical verses in preprocessing_v1.")
    if manifest.get("packet_count") != 190:
        die("Expected 190 preprocessing packets.")

    packets = {}
    for entry in manifest.get("packets", []):
        packet_path = pre / entry["filename"]
        packet = read_json(packet_path)
        pid = entry["packet_id"]
        if packet.get("packet_id") != pid:
            die(f"Packet identity mismatch: {packet_path}")
        if packet.get("source", {}).get("source_sha256") != report.get("source_sha256"):
            die(f"Source SHA mismatch in packet: {pid}")
        packets[pid] = packet

    if len(packets) != 190:
        die(f"Expected 190 unique packets, loaded {len(packets)}.")
    return report, manifest, packets


def build_request(packet: dict[str, Any], prompt: str, schema: dict[str, Any]):
    packet_text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    return {
        "custom_id": packet["packet_id"],
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
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
                            "text": (
                                "Analyze the following Quran packet under the "
                                "developer instructions and return only the "
                                "required structured output.\n\n"
                                + packet_text
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
        },
    }


def prepare(args) -> int:
    root = args.repo_root.expanduser().resolve()
    run = root / "runs" / args.run_name
    report, packet_manifest, packets = load_preprocessing(root)

    prompt_path = root / PROMPT_REL
    schema_path = root / SCHEMA_REL
    prompt = read_text(prompt_path)
    schema = read_json(schema_path)

    selected = (
        list(PILOT_PACKET_IDS)
        if args.pilot
        else [x["packet_id"] for x in packet_manifest["packets"]]
    )

    missing = [pid for pid in selected if pid not in packets]
    if missing:
        die(f"Selected packet IDs missing from preprocessing: {missing}")
    if len(selected) != len(set(selected)):
        die("Selected packet IDs are not unique.")

    ensure_fresh_dir(run)

    request_path = run / "requests-001.jsonl"
    requests = [build_request(packets[pid], prompt, schema) for pid in selected]
    atomic_write_text(
        request_path,
        "".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n"
            for r in requests
        ),
    )

    if request_path.stat().st_size > MAX_BATCH_FILE_BYTES:
        die("Prepared JSONL exceeds the 200 MB Batch input-file limit.")

    seen = set()
    for line_no, line in enumerate(
        request_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            die(f"Invalid prepared JSONL at line {line_no}: {exc}")
        cid = row.get("custom_id")
        if not cid or cid in seen:
            die(f"Missing/duplicate custom_id at line {line_no}: {cid!r}")
        seen.add(cid)
        body = row.get("body", {})
        if body.get("model") != MODEL:
            die(f"Model mismatch at prepared line {line_no}.")
        if row.get("url") != BATCH_ENDPOINT:
            die(f"Endpoint mismatch at prepared line {line_no}.")
        input_items = body.get("input")
        if not isinstance(input_items, list) or len(input_items) != 2:
            die(f"Unexpected input-message structure at line {line_no}.")
        if input_items[0].get("role") != "developer":
            die(f"Prompt is not developer-role input at line {line_no}.")
        if input_items[1].get("role") != "user":
            die(f"Packet is not user-role input at line {line_no}.")

    if seen != set(selected):
        die("Prepared JSONL custom_id set does not match selected packet set.")

    manifest = {
        "manifest_schema_version": "3.0",
        "task_id": TASK_ID,
        "script_version": SCRIPT_VERSION,
        "created_utc": utc_now(),
        "run_name": args.run_name,
        "selection_mode": "pilot" if args.pilot else "full",
        "packet_count": len(selected),
        "packet_ids": selected,
        "preprocessing_run": "preprocessing_v1",
        "source_sha256": report["source_sha256"],
        "prompt": {
            "path": PROMPT_REL,
            "sha256": sha256_file(prompt_path),
        },
        "schema": {
            "path": SCHEMA_REL,
            "sha256": sha256_file(schema_path),
            "name": SCHEMA_NAME,
        },
        "request_file": {
            "path": "requests-001.jsonl",
            "sha256": sha256_file(request_path),
            "bytes": request_path.stat().st_size,
        },
        "api_configuration": {
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "endpoint": BATCH_ENDPOINT,
            "completion_window": COMPLETION_WINDOW,
            "structured_output_strict": True,
            "prompt_transport": "developer-role input message",
            "sdk_automatic_retries": 0,
            "automatic_paid_retry": False,
        },
        "api_state": {
            "input_file_id": None,
            "input_file_uploaded_utc": None,
            "batch_id": None,
            "batch_created_utc": None,
            "last_known_batch_status": None,
            "last_status_checked_utc": None,
            "submission_error": None,
        },
        "status": "PREPARED",
    }
    atomic_write_json(run / "manifest.json", manifest)

    prep_report = f"""NAMES OF ALLAH — PHASE 1 BATCH PREPARE
=========================================

Status: PREPARED
Prompt: v3.2
Schema: v3.0
Run: {args.run_name}
Selection: {manifest['selection_mode']}
Requests: {len(selected)}
Model: {MODEL}
Reasoning: {REASONING_EFFORT}
Max output tokens/request: {MAX_OUTPUT_TOKENS}
Prompt transport: developer-role input message
Request bytes: {manifest['request_file']['bytes']}

Source SHA-256:
{manifest['source_sha256']}

Prompt SHA-256:
{manifest['prompt']['sha256']}

Schema SHA-256:
{manifest['schema']['sha256']}

Request JSONL SHA-256:
{manifest['request_file']['sha256']}

NO API CALL WAS MADE.
"""
    atomic_write_text(run / "prepare_report.txt", prep_report)
    print(prep_report, end="")
    return 0


def load_run(root: Path, run_name: str):
    run = root / "runs" / run_name
    manifest = read_json(run / "manifest.json")
    if manifest.get("task_id") != TASK_ID:
        die(f"Unexpected task_id in {run / 'manifest.json'}")
    return run, manifest


def persist_manifest(run: Path, manifest: dict[str, Any]) -> None:
    atomic_write_json(run / "manifest.json", manifest)


def submit(args) -> int:
    if not args.confirm_api:
        die("Paid Batch submission requires --confirm-api.")

    root = args.repo_root.expanduser().resolve()
    run, manifest = load_run(root, args.run_name)

    if manifest.get("status") != "PREPARED":
        die(f"Run status is {manifest.get('status')!r}; expected PREPARED.")

    state = manifest["api_state"]
    if state.get("batch_id"):
        die(f"Run already has batch_id={state['batch_id']}; refusing duplicate submission.")
    if state.get("input_file_id"):
        die(
            "Run already has an uploaded input_file_id but no batch_id. "
            "Submission outcome may be uncertain. Do not blindly retry."
        )

    request_path = run / manifest["request_file"]["path"]
    if sha256_file(request_path) != manifest["request_file"]["sha256"]:
        die("Prepared request file changed after prepare.")

    c = sdk_client()

    try:
        with request_path.open("rb") as f:
            uploaded = c.files.create(file=f, purpose="batch")
    except Exception as exc:
        state["submission_error"] = {
            "stage": "file_upload",
            "utc": utc_now(),
            "type": type(exc).__name__,
            "message": str(exc),
        }
        persist_manifest(run, manifest)
        raise

    file_id = getattr(uploaded, "id", None)
    if not file_id:
        die("Input-file upload returned no file ID.")

    state["input_file_id"] = file_id
    state["input_file_uploaded_utc"] = utc_now()
    manifest["status"] = "INPUT_UPLOADED"
    persist_manifest(run, manifest)
    atomic_write_json(run / "uploaded_input_file.json", plain(uploaded))

    try:
        batch = c.batches.create(
            input_file_id=file_id,
            endpoint=BATCH_ENDPOINT,
            completion_window=COMPLETION_WINDOW,
            metadata={
                "project": "names_of_Allah",
                "phase": "phase1",
                "run_name": args.run_name,
                "task": TASK_ID,
            },
        )
    except Exception as exc:
        state["submission_error"] = {
            "stage": "batch_create",
            "utc": utc_now(),
            "type": type(exc).__name__,
            "message": str(exc),
            "warning": (
                "Batch creation outcome may be uncertain. Do not automatically "
                "retry. Inspect OpenAI Batch state first."
            ),
        }
        manifest["status"] = "BATCH_CREATE_UNCERTAIN"
        persist_manifest(run, manifest)
        raise

    batch_obj = plain(batch)
    batch_id = batch_obj.get("id")
    if not batch_id:
        die("Batch creation returned no batch ID.")

    state["batch_id"] = batch_id
    state["batch_created_utc"] = utc_now()
    state["last_known_batch_status"] = batch_obj.get("status")
    state["last_status_checked_utc"] = utc_now()
    state["submission_error"] = None
    manifest["status"] = "SUBMITTED"
    persist_manifest(run, manifest)
    atomic_write_json(run / "batch-created.json", batch_obj)

    print(f"Batch ID: {batch_id}")
    print(f"Status: {batch_obj.get('status')}")
    print("No automatic retry will occur.")
    return 0


def status_command(args) -> int:
    root = args.repo_root.expanduser().resolve()
    run, manifest = load_run(root, args.run_name)
    batch_id = manifest["api_state"].get("batch_id")
    if not batch_id:
        die("This run has no batch_id.")

    c = sdk_client()
    batch_obj = plain(c.batches.retrieve(batch_id))
    atomic_write_json(run / f"batch-status-{stamp()}.json", batch_obj)
    atomic_write_json(run / "batch-status-latest.json", batch_obj)

    manifest["api_state"]["last_known_batch_status"] = batch_obj.get("status")
    manifest["api_state"]["last_status_checked_utc"] = utc_now()
    persist_manifest(run, manifest)

    print(json.dumps(batch_obj, ensure_ascii=False, indent=2))
    return 0


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


def literal_occurrence_count(text: str, needle: str) -> int:
    if not needle:
        return 0
    count = 0
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            return count
        count += 1
        start = idx + len(needle)


def exact_match_diagnostic(text: str, needle: str) -> tuple[bool, bool]:
    exact = needle in text
    nfc_only = (
        not exact
        and unicodedata.normalize("NFC", needle)
        in unicodedata.normalize("NFC", text)
    )
    return exact, nfc_only


def _literal_positions(text: str, needle: str) -> list[int]:
    if not needle:
        return []
    positions = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _validate_span_list(
    source: str,
    values: Any,
    *,
    verse_key: str,
    field_name: str,
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []

    if not isinstance(values, list):
        return [{
            "code": f"{field_name.upper()}_NOT_LIST",
            "verse_key": verse_key,
        }]

    # Each returned string must be an exact Quran substring. Duplicates are
    # allowed, but there cannot be more copies than literal source occurrences.
    used_by_value: dict[str, int] = {}
    resolved_positions: list[int] = []

    for item_index, value in enumerate(values, start=1):
        if not isinstance(value, str) or not value:
            problems.append({
                "code": f"EMPTY_{field_name.upper()}",
                "verse_key": verse_key,
                "item_index": item_index,
            })
            continue

        exact, nfc_only = exact_match_diagnostic(source, value)
        if not exact:
            problems.append({
                "code": (
                    f"{field_name.upper()}_NOT_EXACT_SUBSTRING_NFC_EQUIVALENT"
                    if nfc_only
                    else f"{field_name.upper()}_NOT_EXACT_SUBSTRING"
                ),
                "verse_key": verse_key,
                "item_index": item_index,
                "value": value,
            })
            continue

        positions = _literal_positions(source, value)
        occurrence_no = used_by_value.get(value, 0)
        if occurrence_no >= len(positions):
            problems.append({
                "code": f"{field_name.upper()}_DUPLICATE_EXCEEDS_SOURCE_OCCURRENCES",
                "verse_key": verse_key,
                "item_index": item_index,
                "value": value,
                "literal_occurrences_in_source": len(positions),
            })
            continue

        pos = positions[occurrence_no]
        used_by_value[value] = occurrence_no + 1
        resolved_positions.append(pos)

    if resolved_positions != sorted(resolved_positions):
        problems.append({
            "code": f"{field_name.upper()}_NOT_LEFT_TO_RIGHT",
            "verse_key": verse_key,
            "resolved_positions": resolved_positions,
        })

    return problems


ARABIC_DIACRITIC_RE = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)


def _strip_arabic_diacritics(text: str) -> str:
    return ARABIC_DIACRITIC_RE.sub("", text)


STRICT_ALLAH_TOKEN_BARE_RE = re.compile(
    r"^(?:و|ف)?(?:الله|بالله|لله|تالله|اللهم|آلله|أبالله)$"
)

STRICT_MODEL_ALLAH_SURFACE_RE = re.compile(
    r"^(?:اللَّه[َُِ]?|لِلَّه[َُِ]?|اللَّهُمَّ|آللَّه[َُِ]?)$"
)


def _is_strict_allah_source_token(token: str) -> bool:
    """
    Recognize only complete Quran tokens whose lexical item is the proper name
    Allah (possibly with Quran-attested external clitics).

    This deliberately rejects ordinary words that merely contain the same
    undiacritized letter sequence, e.g. اللَّهْوِ, اللَّهَبِ, and
    يُضْلِلْهُ.
    """
    bare = _strip_arabic_diacritics(token)
    return bool(STRICT_ALLAH_TOKEN_BARE_RE.fullmatch(bare))


def _allah_source_tokens(source: str) -> list[str]:
    return [
        token
        for token in source.split()
        if _is_strict_allah_source_token(token)
    ]


def _is_allah_descriptor_surface(value: str) -> bool:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        return False
    return _is_strict_allah_source_token(value)


def _validate_explicit_allah_coverage(
    source: str,
    descriptors: Any,
    *,
    verse_key: str,
) -> list[dict[str, Any]]:
    """
    Deterministic high-confidence guard for the proper name Allah.

    This is a validation gate only. It NEVER retries an API call and NEVER
    edits model output. A mismatch simply prevents structural acceptance.
    """
    if not isinstance(descriptors, list):
        return []

    source_tokens = _allah_source_tokens(source)
    returned = [
        x for x in descriptors
        if isinstance(x, str) and _is_allah_descriptor_surface(x)
    ]

    if len(returned) != len(source_tokens):
        return [{
            "code": "ALLAH_OCCURRENCE_COUNT_MISMATCH",
            "verse_key": verse_key,
            "expected_explicit_allah_occurrences": len(source_tokens),
            "returned_allah_descriptors": len(returned),
            "source_tokens": source_tokens,
            "returned_values": returned,
        }]

    return []



def _non_diacritic_index_map(text: str) -> tuple[str, list[int]]:
    bare_chars = []
    index_map = []
    for idx, ch in enumerate(text):
        if ARABIC_DIACRITIC_RE.fullmatch(ch):
            continue
        bare_chars.append(ch)
        index_map.append(idx)
    return "".join(bare_chars), index_map


def _expected_allah_surface_occurrences(source: str) -> list[dict[str, Any]]:
    """
    Deterministically identify explicit written occurrences of the proper name
    Allah and the Phase-1 surface span expected under the prompt's clitic rule.

    This is safe because an explicit written occurrence of the proper name
    Allah is not a semantic classification problem.
    """
    out = []
    cursor = 0

    for token in source.split():
        token_start = source.find(token, cursor)
        if token_start < 0:
            continue
        cursor = token_start + len(token)

        bare, idx_map = _non_diacritic_index_map(token)

        if not _is_strict_allah_source_token(token):
            continue

        # Interrogative hamza fused orthographically with Allah:
        # آللَّهُ. Preserve the entire written token because اللَّهُ is not a
        # literal contiguous substring of this Quran spelling.
        if bare == "آلله":
            out.append({
                "surface": token,
                "start": token_start,
                "source_token": token,
            })
            continue

        # Special vocative form: اللَّهُمَّ (possibly with removable و/ف prefix).
        idx_allahumma = bare.find("اللهم")
        if idx_allahumma >= 0:
            start_orig = idx_map[idx_allahumma]
            surface = token[start_orig:]
            out.append({
                "surface": surface,
                "start": token_start + start_orig,
                "source_token": token,
            })
            continue

        # Ordinary form where the written alif of اللَّه is present.
        idx_allah = bare.find("الله")
        if idx_allah >= 0:
            start_orig = idx_map[idx_allah]
            surface = token[start_orig:]
            out.append({
                "surface": surface,
                "start": token_start + start_orig,
                "source_token": token,
            })
            continue

        # Fused lām-preposition spelling such as لِلَّهِ / فَلِلَّهِ / وَلِلَّهِ.
        idx_lillah = bare.find("لله")
        if idx_lillah >= 0:
            start_orig = idx_map[idx_lillah]
            surface = token[start_orig:]
            out.append({
                "surface": surface,
                "start": token_start + start_orig,
                "source_token": token,
            })

    return out


def _resolve_list_positions(source: str, values: list[str]) -> list[tuple[int, str]]:
    used: dict[str, int] = {}
    resolved: list[tuple[int, str]] = []
    for value in values:
        positions = _literal_positions(source, value)
        n = used.get(value, 0)
        if n >= len(positions):
            # Leave unresolved values at the end; ordinary validation will fail
            # them later. Do not silently repair non-Allah descriptors.
            resolved.append((len(source) + len(resolved), value))
        else:
            resolved.append((positions[n], value))
            used[value] = n + 1
    return resolved


def reconcile_explicit_allah(
    packet: dict[str, Any],
    parsed: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Deterministically reconcile ONLY the explicit proper name Allah.

    Raw/model output remains preserved separately. This function:
    - removes model-supplied Allah surfaces from descriptors/manual_review;
    - inserts the exact expected Allah surfaces from the Quran source;
    - restores left-to-right descriptor order;
    - records every change.

    It never changes any non-Allah semantic finding and never triggers an API
    retry.
    """
    reconciled = copy.deepcopy(parsed)
    repairs: list[dict[str, Any]] = []

    core_text = {x["verse_key"]: x["text"] for x in packet["core_verses"]}

    for verse_result in reconciled.get("verse_results", []):
        if not isinstance(verse_result, dict):
            continue
        verse_key = verse_result.get("verse_key")
        source = core_text.get(verse_key)
        if source is None:
            continue

        descriptors = verse_result.get("descriptors")
        manual = verse_result.get("manual_review")
        if not isinstance(descriptors, list) or not isinstance(manual, list):
            continue

        expected = _expected_allah_surface_occurrences(source)
        expected_values = [x["surface"] for x in expected]

        model_allah = [
            x for x in descriptors
            if isinstance(x, str) and _is_allah_descriptor_surface(x)
        ]
        model_manual_allah = [
            x for x in manual
            if isinstance(x, str) and _is_allah_descriptor_surface(x)
        ]

        non_allah_descriptors = [
            x for x in descriptors
            if not (isinstance(x, str) and _is_allah_descriptor_surface(x))
        ]
        non_allah_manual = [
            x for x in manual
            if not (isinstance(x, str) and _is_allah_descriptor_surface(x))
        ]

        # Merge deterministic Allah surfaces with untouched model descriptors.
        positioned = _resolve_list_positions(source, non_allah_descriptors)
        positioned.extend((x["start"], x["surface"]) for x in expected)
        positioned.sort(key=lambda pair: pair[0])

        new_descriptors = [value for _, value in positioned]
        verse_result["descriptors"] = new_descriptors
        verse_result["manual_review"] = non_allah_manual

        if model_allah != expected_values or model_manual_allah:
            repairs.append({
                "code": "DETERMINISTIC_ALLAH_RECONCILIATION",
                "verse_key": verse_key,
                "model_allah_descriptors": model_allah,
                "model_allah_manual_review": model_manual_allah,
                "expected_allah_surfaces": expected_values,
                "source_tokens": [x["source_token"] for x in expected],
            })

    return reconciled, repairs


def validate_parsed(packet: dict[str, Any], parsed: dict[str, Any]):
    problems: list[dict[str, Any]] = []
    packet_id = packet["packet_id"]

    core_text = {x["verse_key"]: x["text"] for x in packet["core_verses"]}
    expected_keys = [x["verse_key"] for x in packet["core_verses"]]

    if parsed.get("packet_id") != packet_id:
        problems.append({
            "code": "PACKET_ID_MISMATCH",
            "expected": packet_id,
            "actual": parsed.get("packet_id"),
        })

    results = parsed.get("verse_results")
    if not isinstance(results, list):
        return problems + [{"code": "VERSE_RESULTS_NOT_LIST"}]

    actual_keys = [x.get("verse_key") for x in results if isinstance(x, dict)]
    if actual_keys != expected_keys:
        problems.append({
            "code": "CORE_VERSE_COVERAGE_OR_ORDER_MISMATCH",
            "expected": expected_keys,
            "actual": actual_keys,
        })

    for result in results:
        if not isinstance(result, dict):
            problems.append({"code": "VERSE_RESULT_NOT_OBJECT"})
            continue

        verse_key = result.get("verse_key")
        if verse_key not in core_text:
            problems.append({
                "code": "CONTEXT_OR_UNKNOWN_VERSE_RESULT",
                "verse_key": verse_key,
            })
            continue

        source = core_text[verse_key]

        problems.extend(
            _validate_span_list(
                source,
                result.get("descriptors"),
                verse_key=verse_key,
                field_name="descriptors",
            )
        )
        problems.extend(
            _validate_span_list(
                source,
                result.get("manual_review"),
                verse_key=verse_key,
                field_name="manual_review",
            )
        )

        problems.extend(
            _validate_explicit_allah_coverage(
                source,
                result.get("descriptors"),
                verse_key=verse_key,
            )
        )

        descriptors = result.get("descriptors")
        manual = result.get("manual_review")
        if isinstance(descriptors, list) and isinstance(manual, list):
            overlap = sorted(
                set(x for x in descriptors if isinstance(x, str))
                & set(x for x in manual if isinstance(x, str))
            )
            if overlap:
                problems.append({
                    "code": "SAME_STRING_IN_DESCRIPTORS_AND_MANUAL_REVIEW",
                    "verse_key": verse_key,
                    "values": overlap,
                })

    return problems



def load_prepared_requests(run: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    request_path = run / manifest["request_file"]["path"]

    if sha256_file(request_path) != manifest["request_file"]["sha256"]:
        die("Prepared request file changed after prepare.")

    rows: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(
        request_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            die(f"Invalid prepared JSONL at line {line_no}: {exc}")

        cid = row.get("custom_id")
        if not cid:
            die(f"Prepared JSONL line {line_no} has no custom_id.")
        if cid in rows:
            die(f"Duplicate custom_id in prepared JSONL: {cid}")
        rows[cid] = row

    expected = list(manifest["packet_ids"])
    if set(rows) != set(expected):
        die(
            "Prepared JSONL custom_id set no longer matches the run manifest. "
            "Refusing API calls."
        )

    return rows


def pilot_sync(args) -> int:
    """
    Execute the already-prepared six-request pilot through normal synchronous
    Responses API calls instead of OpenAI Batch.

    This command is intentionally restricted to a run prepared with --pilot.
    It preserves each raw API response before any parsing or validation and
    performs no automatic API or semantic retry.
    """
    if not args.confirm_api:
        die("Paid synchronous pilot requires --confirm-api.")

    root = args.repo_root.expanduser().resolve()
    run, manifest = load_run(root, args.run_name)

    if manifest.get("selection_mode") != "pilot":
        die(
            "pilot-sync may only be used on a run prepared with --pilot. "
            "Use Batch for the full corpus."
        )
    if manifest.get("packet_count") != len(PILOT_PACKET_IDS):
        die(
            f"Expected exactly {len(PILOT_PACKET_IDS)} pilot packets; "
            f"manifest has {manifest.get('packet_count')}."
        )
    if set(manifest.get("packet_ids", [])) != set(PILOT_PACKET_IDS):
        die("Pilot packet set does not match the frozen six-packet pilot.")

    if getattr(args, "packet_id", None):
        selected_packet_ids = list(dict.fromkeys(args.packet_id))
        unknown = [
            pid for pid in selected_packet_ids
            if pid not in manifest.get("packet_ids", [])
        ]
        if unknown:
            die(f"Requested --packet-id is not in the frozen pilot set: {unknown}")
    else:
        selected_packet_ids = list(manifest["packet_ids"])

    api_state = manifest.get("api_state", {})
    if api_state.get("batch_id") or api_state.get("input_file_id"):
        die(
            "This run already contains Batch API state. Refusing to mix "
            "synchronous pilot calls with a Batch submission."
        )

    sync_root = run / "sync-pilot"
    if sync_root.exists() and any(sync_root.iterdir()):
        die(
            f"Synchronous pilot evidence already exists at: {sync_root}\n"
            "Refusing to rerun paid requests automatically. Inspect the prior "
            "run or create a new --run-name."
        )

    raw_dir = sync_root / "raw_responses"
    attempts_dir = sync_root / "attempts"
    error_dir = sync_root / "api_errors"
    raw_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    requests_by_id = load_prepared_requests(run, manifest)
    _, _, packets = load_preprocessing(root)

    sync_state = {
        "mode": "synchronous_responses_api",
        "started_utc": utc_now(),
        "completed_utc": None,
        "script_version": SCRIPT_VERSION,
        "automatic_sdk_retries": 0,
        "automatic_semantic_retries": False,
        "selected_packet_ids": selected_packet_ids,
        "attempted_packet_ids": [],
        "completed_packet_ids": [],
        "api_error_packet_ids": [],
    }
    manifest["sync_pilot_state"] = sync_state
    manifest["status"] = "SYNC_PILOT_RUNNING"
    persist_manifest(run, manifest)

    c = sdk_client()
    counters = Counter()
    issue_codes = Counter()
    extraction_counts = Counter()
    per_packet = []
    total_usage = Counter()

    for request_number, pid in enumerate(selected_packet_ids, start=1):
        row = requests_by_id[pid]
        body = row.get("body")
        if not isinstance(body, dict):
            die(f"Prepared request body missing for {pid}.")

        sync_state["attempted_packet_ids"].append(pid)
        persist_manifest(run, manifest)

        print(
            f"[{request_number}/{len(selected_packet_ids)}] "
            f"Calling Responses API for {pid} ..."
        )

        request_started = utc_now()
        try:
            response = c.responses.create(**body)
        except Exception as exc:
            error_record = {
                "packet_id": pid,
                "request_started_utc": request_started,
                "failed_utc": utc_now(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "automatic_retry_performed": False,
            }
            atomic_write_json(error_dir / f"{pid}.json", error_record)

            sync_state["api_error_packet_ids"].append(pid)
            sync_state["completed_utc"] = utc_now()
            manifest["status"] = "SYNC_PILOT_STOPPED_ON_API_ERROR"
            persist_manifest(run, manifest)

            report = {
                "report_schema_version": "3.0",
                "task_id": TASK_ID,
                "run_name": args.run_name,
                "mode": "synchronous_responses_api",
                "status": "STOPPED_ON_API_ERROR",
                "failed_packet_id": pid,
                "completed_before_error": list(sync_state["completed_packet_ids"]),
                "error_record": error_record,
                "automatic_retry_performed": False,
            }
            atomic_write_json(sync_root / "pilot_sync_report.json", report)
            atomic_write_text(
                sync_root / "pilot_sync_report.txt",
                (
                    "NAMES OF ALLAH — SYNCHRONOUS PILOT\n"
                    "====================================\n\n"
                    "Status: STOPPED_ON_API_ERROR\n"
                    f"Failed packet: {pid}\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error: {exc}\n\n"
                    "No automatic retry was performed.\n"
                    "Do not rerun this paid pilot blindly; inspect the saved "
                    "error first.\n"
                ),
            )
            print(f"API ERROR on {pid}: {type(exc).__name__}: {exc}")
            print("Pilot stopped. No automatic retry was performed.")
            return 2

        raw = plain(response)

        # Persist the paid API result BEFORE parsing or validation.
        atomic_write_json(raw_dir / f"{pid}.json", raw)

        usage = raw.get("usage") or {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                total_usage[key] += value

        response_status = raw.get("status")
        text_output, refusal = response_output_text(raw)

        attempt = {
            "packet_id": pid,
            "request_started_utc": request_started,
            "response_saved_utc": utc_now(),
            "response_id": raw.get("id"),
            "response_status": response_status,
            "usage": usage,
            "raw_response_file": f"raw_responses/{pid}.json",
            "collection_status": None,
            "refusal": refusal,
            "model_parsed_output": None,
            "parsed_output": None,
            "deterministic_repairs": [],
            "structural_findings": [],
        }

        if response_status == "incomplete" or raw.get("incomplete_details"):
            counters["response_incomplete"] += 1

        if refusal:
            counters["refused"] += 1
            attempt["collection_status"] = "REFUSED"

        elif not text_output:
            counters["parse_failed"] += 1
            attempt["collection_status"] = "PARSE_FAILED"
            attempt["structural_findings"] = [{"code": "NO_OUTPUT_TEXT"}]

        else:
            try:
                parsed = json.loads(text_output)
            except json.JSONDecodeError as exc:
                counters["parse_failed"] += 1
                attempt["collection_status"] = "PARSE_FAILED"
                attempt["raw_output_text"] = text_output
                attempt["structural_findings"] = [{
                    "code": "JSON_PARSE_FAILED",
                    "message": str(exc),
                }]
            else:
                attempt["model_parsed_output"] = parsed
                reconciled, deterministic_repairs = reconcile_explicit_allah(
                    packets[pid], parsed
                )
                attempt["parsed_output"] = reconciled
                attempt["deterministic_repairs"] = deterministic_repairs
                structural = validate_parsed(packets[pid], reconciled)
                attempt["structural_findings"] = structural

                for problem in structural:
                    issue_codes[problem["code"]] += 1

                for verse_result in parsed.get("verse_results", []):
                    if not isinstance(verse_result, dict):
                        continue
                    descriptors = verse_result.get("descriptors")
                    manual = verse_result.get("manual_review")
                    if isinstance(descriptors, list):
                        extraction_counts["descriptors"] += len(descriptors)
                    if isinstance(manual, list):
                        extraction_counts["manual_review"] += len(manual)

                if structural:
                    counters["structural_validation_failed"] += 1
                    attempt["collection_status"] = "STRUCTURAL_VALIDATION_FAILED"
                else:
                    counters["structurally_accepted"] += 1
                    attempt["collection_status"] = "STRUCTURALLY_ACCEPTED"

        atomic_write_json(attempts_dir / f"{pid}__attempt-1.json", attempt)

        sync_state["completed_packet_ids"].append(pid)
        persist_manifest(run, manifest)

        per_packet.append({
            "packet_id": pid,
            "response_id": raw.get("id"),
            "response_status": response_status,
            "collection_status": attempt["collection_status"],
            "structural_finding_count": len(attempt["structural_findings"]),
            "usage": usage,
        })

        print(
            f"[{request_number}/{len(selected_packet_ids)}] "
            f"{pid}: {attempt['collection_status']}"
        )

    sync_state["completed_utc"] = utc_now()

    has_issues = any(
        counters.get(key, 0)
        for key in (
            "response_incomplete",
            "refused",
            "parse_failed",
            "structural_validation_failed",
        )
    )

    final_status = (
        "SYNC_PILOT_COMPLETED_WITH_ISSUES"
        if has_issues
        else "SYNC_PILOT_COMPLETED"
    )
    manifest["status"] = final_status
    persist_manifest(run, manifest)

    report = {
        "report_schema_version": "2.0.2",
        "task_id": TASK_ID,
        "run_name": args.run_name,
        "mode": "synchronous_responses_api",
        "status": final_status,
        "started_utc": sync_state["started_utc"],
        "completed_utc": sync_state["completed_utc"],
        "expected_request_count": len(selected_packet_ids),
        "completed_request_count": len(sync_state["completed_packet_ids"]),
        "counters": dict(counters),
        "extraction_counts": dict(extraction_counts),
        "structural_issue_codes": dict(issue_codes),
        "usage_totals": dict(total_usage),
        "per_packet": per_packet,
        "automatic_sdk_retries": 0,
        "automatic_semantic_retries": False,
    }
    atomic_write_json(sync_root / "pilot_sync_report.json", report)

    summary = f"""NAMES OF ALLAH — SYNCHRONOUS PHASE 1 PILOT
===========================================

Status: {final_status}
Run: {args.run_name}
Mode: normal synchronous Responses API
Requests attempted: {len(sync_state['attempted_packet_ids'])}
Requests completed: {len(sync_state['completed_packet_ids'])}

Structurally accepted: {counters.get('structurally_accepted', 0)}
Structural validation failed: {counters.get('structural_validation_failed', 0)}
Parse failed: {counters.get('parse_failed', 0)}
Refused: {counters.get('refused', 0)}
Incomplete responses: {counters.get('response_incomplete', 0)}

Descriptors: {extraction_counts.get('descriptors', 0)}
Manual review candidates: {extraction_counts.get('manual_review', 0)}

Input tokens: {total_usage.get('input_tokens', 0)}
Output tokens: {total_usage.get('output_tokens', 0)}
Total tokens: {total_usage.get('total_tokens', 0)}

Raw API responses were saved before parsing.
No automatic retry was performed.
"""
    atomic_write_text(sync_root / "pilot_sync_report.txt", summary)
    print()
    print(summary, end="")
    return 0



def collect(args) -> int:
    root = args.repo_root.expanduser().resolve()
    run, manifest = load_run(root, args.run_name)
    batch_id = manifest["api_state"].get("batch_id")
    if not batch_id:
        die("This run has no batch_id.")

    c = sdk_client()
    batch_obj = plain(c.batches.retrieve(batch_id))
    atomic_write_json(run / "batch-status-at-collection.json", batch_obj)

    if batch_obj.get("status") not in TERMINAL_BATCH_STATUSES:
        die(f"Batch is not terminal: {batch_obj.get('status')}")

    raw_output = ""
    raw_errors = ""

    if batch_obj.get("output_file_id"):
        raw_output = c.files.content(batch_obj["output_file_id"]).text
        atomic_write_text(run / "batch-001-output.jsonl", raw_output)

    if batch_obj.get("error_file_id"):
        raw_errors = c.files.content(batch_obj["error_file_id"]).text
        atomic_write_text(run / "batch-001-errors.jsonl", raw_errors)

    # Raw files are persisted before parsing starts.
    _, _, packets = load_preprocessing(root)
    expected = set(manifest["packet_ids"])
    attempts_dir = run / "attempts"
    attempts_dir.mkdir(exist_ok=True)

    outputs = {}
    errors = {}
    malformed_output = []
    malformed_error = []
    duplicate_output_ids = []

    for line_no, line in enumerate(raw_output.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            malformed_output.append({"line": line_no, "error": str(exc)})
            continue
        cid = row.get("custom_id")
        if cid in outputs:
            duplicate_output_ids.append(cid)
        else:
            outputs[cid] = row

    for line_no, line in enumerate(raw_errors.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            malformed_error.append({"line": line_no, "error": str(exc)})
            continue
        errors[row.get("custom_id")] = row

    counters = Counter()
    issue_codes = Counter()
    per_packet = []

    for pid in manifest["packet_ids"]:
        packet = packets[pid]

        if pid in errors:
            counters["request_failed"] += 1
            attempt = {
                "packet_id": pid,
                "collection_status": "REQUEST_FAILED",
                "collected_utc": utc_now(),
                "api_error_line": errors[pid],
                "parsed_output": None,
                "structural_findings": [],
            }
            atomic_write_json(attempts_dir / f"{pid}__attempt-1.json", attempt)
            per_packet.append({"packet_id": pid, "status": "REQUEST_FAILED"})
            continue

        row = outputs.get(pid)
        if row is None:
            counters["missing_result"] += 1
            per_packet.append({"packet_id": pid, "status": "MISSING_RESULT"})
            continue

        response = row.get("response") or {}
        body = response.get("body") or {}

        if response.get("status_code") != 200:
            counters["request_failed"] += 1
            attempt = {
                "packet_id": pid,
                "collection_status": "REQUEST_FAILED",
                "collected_utc": utc_now(),
                "api_output_line": row,
                "parsed_output": None,
                "structural_findings": [],
            }
            atomic_write_json(attempts_dir / f"{pid}__attempt-1.json", attempt)
            per_packet.append({"packet_id": pid, "status": "REQUEST_FAILED"})
            continue

        text, refusal = response_output_text(body)

        if refusal:
            counters["refused"] += 1
            attempt = {
                "packet_id": pid,
                "collection_status": "REFUSED",
                "collected_utc": utc_now(),
                "api_output_line": row,
                "refusal": refusal,
                "parsed_output": None,
                "structural_findings": [],
            }
            atomic_write_json(attempts_dir / f"{pid}__attempt-1.json", attempt)
            per_packet.append({"packet_id": pid, "status": "REFUSED"})
            continue

        if body.get("status") == "incomplete" or body.get("incomplete_details"):
            counters["response_incomplete"] += 1

        if not text:
            counters["parse_failed"] += 1
            attempt = {
                "packet_id": pid,
                "collection_status": "PARSE_FAILED",
                "collected_utc": utc_now(),
                "api_output_line": row,
                "parsed_output": None,
                "structural_findings": [{"code": "NO_OUTPUT_TEXT"}],
            }
            atomic_write_json(attempts_dir / f"{pid}__attempt-1.json", attempt)
            per_packet.append({"packet_id": pid, "status": "PARSE_FAILED"})
            continue

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            counters["parse_failed"] += 1
            attempt = {
                "packet_id": pid,
                "collection_status": "PARSE_FAILED",
                "collected_utc": utc_now(),
                "api_output_line": row,
                "raw_output_text": text,
                "parsed_output": None,
                "structural_findings": [{
                    "code": "JSON_PARSE_FAILED",
                    "message": str(exc),
                }],
            }
            atomic_write_json(attempts_dir / f"{pid}__attempt-1.json", attempt)
            per_packet.append({"packet_id": pid, "status": "PARSE_FAILED"})
            continue

        reconciled, deterministic_repairs = reconcile_explicit_allah(
            packet, parsed
        )
        structural = validate_parsed(packet, reconciled)
        for problem in structural:
            issue_codes[problem["code"]] += 1

        if structural:
            status_name = "STRUCTURAL_VALIDATION_FAILED"
            counters["structural_validation_failed"] += 1
        else:
            status_name = "STRUCTURALLY_ACCEPTED"
            counters["structurally_accepted"] += 1

        attempt = {
            "packet_id": pid,
            "collection_status": status_name,
            "collected_utc": utc_now(),
            "api_output_line": row,
            "model_parsed_output": parsed,
            "parsed_output": reconciled,
            "deterministic_repairs": deterministic_repairs,
            "structural_findings": structural,
        }
        atomic_write_json(attempts_dir / f"{pid}__attempt-1.json", attempt)
        per_packet.append({
            "packet_id": pid,
            "status": status_name,
            "structural_finding_count": len(structural),
        })

    report = {
        "report_schema_version": "3.0",
        "task_id": TASK_ID,
        "run_name": args.run_name,
        "batch_id": batch_id,
        "batch_status": batch_obj.get("status"),
        "collected_utc": utc_now(),
        "expected_request_count": len(expected),
        "counters": dict(counters),
        "structural_issue_codes": dict(issue_codes),
        "duplicate_output_ids": duplicate_output_ids,
        "unexpected_output_ids": sorted(set(outputs) - expected),
        "unexpected_error_ids": sorted(set(errors) - expected),
        "missing_ids": sorted(expected - set(outputs) - set(errors)),
        "malformed_output_lines": malformed_output,
        "malformed_error_lines": malformed_error,
        "per_packet": per_packet,
    }
    atomic_write_json(run / "collection_report.json", report)

    manifest["api_state"]["last_known_batch_status"] = batch_obj.get("status")
    manifest["api_state"]["last_status_checked_utc"] = utc_now()
    manifest["status"] = "COLLECTED"
    manifest["collection_report"] = "collection_report.json"
    persist_manifest(run, manifest)

    summary = f"""NAMES OF ALLAH — PHASE 1 COLLECTION
=====================================

Run: {args.run_name}
Batch ID: {batch_id}
Batch status: {batch_obj.get('status')}
Expected requests: {len(expected)}
Structurally accepted: {counters.get('structurally_accepted', 0)}
Structural validation failed: {counters.get('structural_validation_failed', 0)}
Parse failed: {counters.get('parse_failed', 0)}
Refused: {counters.get('refused', 0)}
Request failed: {counters.get('request_failed', 0)}
Missing result: {counters.get('missing_result', 0)}
Response incomplete: {counters.get('response_incomplete', 0)}

No failed semantic request was automatically retried.
"""
    atomic_write_text(run / "collection_report.txt", summary)
    print(summary, end="")
    return 0


def parse_args():
    default_root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(
        description="Phase 1 Names-of-Allah OpenAI Batch workflow."
    )
    p.add_argument("--repo-root", type=Path, default=default_root)

    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("prepare", help="Prepare JSONL locally; NO API CALL.")
    q.add_argument("--run-name", required=True)
    q.add_argument("--pilot", action="store_true")

    q = sub.add_parser("submit", help="Submit a paid Batch.")
    q.add_argument("--run-name", required=True)
    q.add_argument("--confirm-api", action="store_true")

    q = sub.add_parser(
        "pilot-sync",
        help="Run the frozen pilot synchronously; paid API calls.",
    )
    q.add_argument("--run-name", required=True)
    q.add_argument(
        "--packet-id",
        action="append",
        help=(
            "Optional frozen pilot packet ID to run. Repeat for multiple IDs. "
            "If omitted, all six pilot packets run."
        ),
    )
    q.add_argument("--confirm-api", action="store_true")

    q = sub.add_parser("status", help="Retrieve Batch status.")
    q.add_argument("--run-name", required=True)

    q = sub.add_parser("collect", help="Download raw results then validate.")
    q.add_argument("--run-name", required=True)

    return p.parse_args()


def main():
    args = parse_args()
    if args.command == "prepare":
        return prepare(args)
    if args.command == "submit":
        return submit(args)
    if args.command == "pilot-sync":
        return pilot_sync(args)
    if args.command == "status":
        return status_command(args)
    if args.command == "collect":
        return collect(args)
    die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
