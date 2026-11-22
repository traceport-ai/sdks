#!/usr/bin/env python3
"""Validate the shared contract snapshot and fixtures. Standard library only.

Errors fail the run. Warnings are printed but do not fail it.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DIR = ROOT / "contract"
FIXTURES_DIR = ROOT / "fixtures"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
FORBIDDEN_PATH_PARTS = ("/dashboard",)
FORBIDDEN_SCHEMES = ("DashboardBearer",)
CREDENTIAL_HEADERS = {"authorization", "x-api-key"}
FIXTURE_KINDS = {"resource", "outcome", "error"}
SOURCE_KINDS = {"recorded", "derived"}
OUTCOME_STATUSES = {"succeeded", "failed"}
ERROR_KEYS = {"class", "status", "errorCode", "retryable"}
SOURCE_KEYS = {"repository", "path", "ref", "commit", "uncommittedChanges", "sha256"}
# Implementation details that should not appear in public API descriptions.
INTERNAL_TERMS = re.compile(r"\b(?:goroutines?|asynq|postgres(?:ql)?|middleware|redis)\b", re.IGNORECASE)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def load_json(path: Path, report: Report) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        report.error(str(path.relative_to(ROOT)), f"invalid JSON: {exc}")
        return None


def walk(node: Any, trail: str = ""):
    yield trail, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{trail}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{trail}/{index}")


def resolve_ref(spec: dict[str, Any], ref: str) -> bool:
    if not ref.startswith("#/"):
        return False
    node: Any = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def check_contract(report: Report) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Return operationId -> (method, path template, operation)."""
    where = "contract/openapi.json"
    allow = load_json(CONTRACT_DIR / "public-operations.json", report)
    spec = load_json(CONTRACT_DIR / "openapi.json", report)
    source = load_json(CONTRACT_DIR / "SOURCE.json", report)
    if allow is None or spec is None:
        return {}

    if not str(spec.get("openapi", "")).startswith("3."):
        report.error(where, "openapi version must be 3.x")
    if not spec.get("servers"):
        report.error(where, "servers must be set")

    operations: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for path, item in spec.get("paths", {}).items():
        if any(part in path for part in FORBIDDEN_PATH_PARTS):
            report.error(where, f"non-public path {path}")
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                report.error(where, f"{method.upper()} {path} has no operationId")
                continue
            operations[operation_id] = (method.upper(), path, operation)

    expected = set(allow.get("operations", []))
    for operation_id in sorted(expected - set(operations)):
        report.error(where, f"listed operation {operation_id} is missing; re-export the contract")
    for operation_id in sorted(set(operations) - expected):
        report.error(where, f"operation {operation_id} is not in public-operations.json")

    schemes = spec.get("components", {}).get("securitySchemes", {})
    for name in FORBIDDEN_SCHEMES:
        if name in schemes:
            report.error(where, f"non-public security scheme {name}")

    for trail, node in walk(spec):
        if isinstance(node, dict) and isinstance(node.get("$ref"), str) and not resolve_ref(spec, node["$ref"]):
            report.error(where, f"unresolved $ref {node['$ref']} at {trail}")
        if trail.endswith(("/description", "/summary")) and isinstance(node, str):
            for term in sorted({m.group(0).lower() for m in INTERNAL_TERMS.finditer(node)}):
                report.error(where, f"internal term '{term}' in {trail}")

    if source is not None:
        missing = SOURCE_KEYS - set(source)
        if missing:
            report.error("contract/SOURCE.json", "missing keys: " + ", ".join(sorted(missing)))
        elif source["uncommittedChanges"]:
            report.warn("contract/SOURCE.json", "snapshot was exported from uncommitted backend changes")
    return operations


def path_matches(template: str, actual: str) -> bool:
    pattern = "^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template)) + "$"
    return re.match(pattern, actual.split("?", 1)[0]) is not None


def check_fixtures(report: Report, operations: dict[str, tuple[str, str, dict[str, Any]]]) -> int:
    names: dict[str, str] = {}
    count = 0
    derived = 0
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        count += 1
        where = str(path.relative_to(ROOT))
        fixture = load_json(path, report)
        if not isinstance(fixture, dict):
            if fixture is not None:
                report.error(where, "fixture must be a JSON object")
            continue

        missing = {"name", "source", "operation", "request", "response", "expect"} - set(fixture)
        if missing:
            report.error(where, "missing keys: " + ", ".join(sorted(missing)))
            continue

        source = fixture["source"]
        if not isinstance(source, dict) or source.get("kind") not in SOURCE_KINDS or not source.get("from"):
            report.error(where, f"source must be {{kind: one of {sorted(SOURCE_KINDS)}, from: ...}}")
        elif source["kind"] == "derived":
            derived += 1
        else:
            try:
                value = source.get("recordedAt")
                if not isinstance(value, str):
                    raise ValueError("missing timestamp")
                recorded = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if recorded.tzinfo is None:
                    raise ValueError("missing timezone")
            except (TypeError, ValueError):
                report.error(where, "recorded source needs a timezone-aware recordedAt timestamp")
            if source.get("capture") not in ("live-http", "isolated-backend-http"):
                report.error(where, "recorded source needs capture=live-http or isolated-backend-http")
            digest = source.get("serverSpecSha256")
            if source.get("capture") == "live-http" and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                report.error(where, "live HTTP recordings need the server OpenAPI SHA-256")

        name = fixture["name"]
        if name in names:
            report.error(where, f"duplicate name {name} (also in {names[name]})")
        names[name] = where

        operation = operations.get(fixture["operation"])
        if operation is None:
            report.error(where, f"unknown operation {fixture['operation']}")
            continue
        method, template, spec_operation = operation

        request = fixture["request"]
        if str(request.get("method", "")).upper() != method:
            report.error(where, f"request.method must be {method}")
        if not path_matches(template, str(request.get("path", ""))):
            report.error(where, f"request.path must match {template}")
        for header in request.get("headers", {}):
            if header.lower() in CREDENTIAL_HEADERS:
                report.error(where, f"request header {header} must not be recorded")

        status = fixture["response"].get("status")
        if str(status) not in spec_operation.get("responses", {}):
            report.error(where, f"response.status {status} is not documented for {fixture['operation']}")

        expect = fixture["expect"]
        kind = expect.get("kind")
        if kind not in FIXTURE_KINDS:
            report.error(where, f"expect.kind must be one of {sorted(FIXTURE_KINDS)}")
        if kind == "error":
            error = expect.get("error")
            if not isinstance(error, dict):
                report.error(where, "expect.error is required when kind is error")
            else:
                missing_error = ERROR_KEYS - set(error)
                if missing_error:
                    report.error(where, "expect.error is missing: " + ", ".join(sorted(missing_error)))
                elif error["status"] != status:
                    report.error(where, "expect.error.status must equal response.status")
        if kind == "outcome" and "outcome" not in expect:
            report.error(where, "expect.outcome is required when kind is outcome")
        if "outcome" in expect:
            outcome = expect["outcome"]
            if not isinstance(outcome, dict) or outcome.get("status") not in OUTCOME_STATUSES or "output" not in outcome:
                report.error(where, f"expect.outcome needs status (one of {sorted(OUTCOME_STATUSES)}) and output")
    if derived:
        report.warn("fixtures", f"{derived} of {count} fixtures are derived from backend code; replace them with recordings")
    return count


def main() -> int:
    report = Report()
    operations = check_contract(report)
    fixture_count = check_fixtures(report, operations)

    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    print(
        f"{len(operations)} public operations, {fixture_count} fixtures, "
        f"{len(report.errors)} errors, {len(report.warnings)} warnings"
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
