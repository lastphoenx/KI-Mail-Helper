#!/usr/bin/env python3
"""Utility to list OpenAI models accessible with the configured API token."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

MIN_PROBE_OUTPUT_TOKENS = 16

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calls the OpenAI /models endpoint with the token from OPENAI_API_KEY "
            "and prints the models the key can access."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        help=(
            "Base URL for the OpenAI API; defaults to https://api.openai.com/v1 or "
            "OPENAI_API_BASE if set."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("OPENAI_API_TIMEOUT", 15)),
        help="Request timeout in seconds (default 15 or OPENAI_API_TIMEOUT).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the raw JSON response instead of a formatted list.",
    )
    parser.add_argument(
        "--env-file",
        default=os.getenv("OPENAI_ENV_FILE", ".env"),
        help="Path to a .env file to read before resolving env vars (default '.env').",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("OPENAI_PROBE_WORKERS", 8)),
        help="Number of concurrent probe workers (default 8).",
    )
    parser.add_argument(
        "--probe-input",
        default=os.getenv("OPENAI_PROBE_INPUT", "ping"),
        help="Prompt text to send during probing (default 'ping').",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=int(os.getenv("OPENAI_PROBE_MAX_TOKENS", 32)),
        help="max_output_tokens value to request when probing (default 32).",
    )
    parser.add_argument(
        "--no-probe",
        dest="probe",
        action="store_false",
        help="Skip per-model test calls and only list models.",
    )
    parser.set_defaults(probe=True)
    return parser.parse_args()


def load_env_file(env_file: str) -> None:
    if not env_file:
        return

    path = Path(env_file)
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        cleaned = value.strip()
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (
            cleaned.startswith("'") and cleaned.endswith("'")
        ):
            cleaned = cleaned[1:-1]

        os.environ[key] = cleaned


def fetch_models(api_key: str, base_url: str, timeout: float) -> Dict[str, Any]:
    if not api_key:
        raise SystemExit("OPENAI_API_KEY env var is missing.")

    endpoint = base_url.rstrip("/") + "/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(endpoint, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise SystemExit(f"Failed to query {endpoint}: {exc}") from exc

    payload: Dict[str, Any] = response.json()
    if "data" not in payload:
        raise SystemExit("Unexpected response payload: missing 'data' field.")
    return payload


@dataclass
class ProbeResult:
    model_id: str
    ok: bool
    status: str
    http_status: Optional[int]
    detail: str


def probe_model(
    model_id: str,
    base_url: str,
    api_key: str,
    timeout: float,
    prompt: str,
    max_output_tokens: int,
) -> ProbeResult:
    endpoint = base_url.rstrip("/") + "/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        return ProbeResult(model_id, False, "network-error", None, str(exc))

    if response.status_code == 200:
        return ProbeResult(model_id, True, "ok", 200, "")

    detail = extract_error_detail(response)
    status = classify_error(response.status_code, detail)
    return ProbeResult(model_id, False, status, response.status_code, detail)


def extract_error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()

    error = payload.get("error")
    if isinstance(error, dict):
        err_type = error.get("type")
        message = error.get("message") or json.dumps(error, sort_keys=True)
        return f"{err_type}: {message}" if err_type else message
    return json.dumps(payload, sort_keys=True)


def classify_error(status_code: int, detail: str) -> str:
    if status_code in (401, 403):
        return "unauthorized"
    if status_code == 404:
        return "not-found"
    if status_code == 429:
        return "rate-limited"
    if status_code == 400 and "unsupported" in detail.lower():
        return "unsupported"
    return "error"


def probe_all_models(
    models: Iterable[Dict[str, Any]],
    base_url: str,
    api_key: str,
    timeout: float,
    prompt: str,
    max_output_tokens: int,
    workers: int,
) -> List[ProbeResult]:
    tasks = [model.get("id", "") for model in models if model.get("id")]
    if not tasks:
        return []

    results: List[ProbeResult] = []
    workers = max(1, workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                probe_model,
                model_id,
                base_url,
                api_key,
                timeout,
                prompt,
                max_output_tokens,
            ): model_id
            for model_id in tasks
        }
        for future in as_completed(future_map):
            model_id = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive
                results.append(
                    ProbeResult(model_id, False, "internal-error", None, str(exc))
                )
    return sorted(results, key=lambda item: item.model_id)


def print_probe_summary(results: List[ProbeResult]) -> None:
    if not results:
        print("No probe results to display.")
        return

    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    print()
    print(f"Probe success: {len(ok)}/{len(results)} models responded with HTTP 200.")

    if failed:
        print("\nFailures:")
        for item in failed:
            status = item.status
            http_info = f"HTTP {item.http_status}" if item.http_status else "no-status"
            detail = item.detail or "(no detail)"
            print(f"- {item.model_id}: {status} ({http_info}) — {detail}")


def print_human_readable(payload: Dict[str, Any]) -> None:
    models = payload.get("data", [])
    if not models:
        print("No models returned for this token.")
        return

    print(f"Token grants access to {len(models)} model(s):")
    for idx, model in enumerate(sorted(models, key=lambda item: item.get("id", "")), start=1):
        model_id = model.get("id", "<unknown>")
        owner = model.get("owned_by", "<unknown>")
        created = model.get("created")
        suffix = f" (created: {created})" if created else ""
        print(f"{idx:3d}. {model_id} — owned by {owner}{suffix}")


def main() -> None:
    args = parse_args()
    load_env_file(args.env_file)
    api_key = os.getenv("OPENAI_API_KEY")
    payload = fetch_models(api_key, args.base_url, args.timeout)
    models = payload.get("data", [])

    if args.json_output:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_human_readable(payload)

    if args.probe:
        if not models:
            print("No models to probe.")
            return

        print("\nStarting per-model probes via /responses ...")
        results = probe_all_models(
            models,
            args.base_url,
            api_key,
            args.timeout,
            args.probe_input,
            max(MIN_PROBE_OUTPUT_TOKENS, args.max_output_tokens),
            args.workers,
        )
        print_probe_summary(results)


if __name__ == "__main__":
    main()
