#!/usr/bin/env python3
"""Export the public SDK contract from the traceport-apis OpenAPI document.

Only operations listed in contract/public-operations.json are exported, together
with the components they reference. Dashboard and internal routes never reach
this public repository.

Usage:
    python3 scripts/export_contract.py <path/to/traceport-apis>          # write snapshot
    python3 scripts/export_contract.py <path/to/traceport-apis> --check  # fail on drift
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DIR = ROOT / "contract"
ALLOWLIST_PATH = CONTRACT_DIR / "public-operations.json"
SNAPSHOT_PATH = CONTRACT_DIR / "openapi.json"
SOURCE_PATH = CONTRACT_DIR / "SOURCE.json"

SOURCE_SPEC = Path("internal/openapi/openapi.json")
SOURCE_REPOSITORY = "traceport-ai/traceport-apis"
PUBLIC_TITLE = "Traceport API"
PUBLIC_DESCRIPTION = (
    "Public Traceport API operations wrapped by the official SDKs. "
    "Exported from traceport-apis by scripts/export_contract.py; do not edit by hand."
)
PUBLIC_SERVERS = [{"url": "https://api.traceport.ai"}]
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


def load_allowlist() -> list[str]:
    data = json.loads(ALLOWLIST_PATH.read_text())
    operations = data["operations"]
    if len(operations) != len(set(operations)):
        raise SystemExit("public-operations.json lists an operationId twice")
    return operations


def collect_refs(node: Any, refs: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.add(value)
            else:
                collect_refs(value, refs)
    elif isinstance(node, list):
        for value in node:
            collect_refs(value, refs)


def split_component_ref(ref: str) -> tuple[str, str]:
    prefix = "#/components/"
    if not ref.startswith(prefix):
        raise SystemExit(f"unsupported $ref (only #/components/... is allowed): {ref}")
    section, _, name = ref[len(prefix):].partition("/")
    if not section or not name or "/" in name:
        raise SystemExit(f"unsupported $ref shape: {ref}")
    return section, name.replace("~1", "/").replace("~0", "~")


def build_contract(source: dict[str, Any], allowlist: list[str]) -> dict[str, Any]:
    wanted = set(allowlist)
    found: dict[str, str] = {}
    paths: dict[str, dict[str, Any]] = {}

    for path, item in source.get("paths", {}).items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            operation_id = operation.get("operationId")
            if operation_id not in wanted:
                continue
            if operation_id in found:
                raise SystemExit(f"operationId {operation_id} appears more than once in the source")
            found[operation_id] = f"{method.upper()} {path}"
            paths.setdefault(path, {})[method] = copy.deepcopy(operation)
        if path in paths and "parameters" in item:
            paths[path]["parameters"] = copy.deepcopy(item["parameters"])

    missing = sorted(wanted - set(found))
    if missing:
        raise SystemExit("operations missing from the source spec: " + ", ".join(missing))

    source_components = source.get("components", {})
    components: dict[str, dict[str, Any]] = {}
    pending: set[str] = set()
    collect_refs(paths, pending)
    seen: set[str] = set()
    while pending:
        ref = pending.pop()
        if ref in seen:
            continue
        seen.add(ref)
        section, name = split_component_ref(ref)
        try:
            target = source_components[section][name]
        except KeyError:
            raise SystemExit(f"unresolved $ref in source spec: {ref}") from None
        components.setdefault(section, {})[name] = copy.deepcopy(target)
        collect_refs(target, pending)

    scheme_names: set[str] = set()
    for item in paths.values():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                for requirement in operation.get("security", source.get("security", [])):
                    scheme_names.update(requirement)
    source_schemes = source_components.get("securitySchemes", {})
    for name in scheme_names:
        if name not in source_schemes:
            raise SystemExit(f"security scheme {name} is not defined in the source spec")
        components.setdefault("securitySchemes", {})[name] = copy.deepcopy(source_schemes[name])

    return {
        "openapi": source["openapi"],
        "info": {
            "title": PUBLIC_TITLE,
            "version": source.get("info", {}).get("version", "0.0.0"),
            "description": PUBLIC_DESCRIPTION,
        },
        "servers": PUBLIC_SERVERS,
        "paths": {path: paths[path] for path in sorted(paths)},
        "components": {
            section: {name: entries[name] for name in sorted(entries)}
            for section, entries in sorted(components.items())
        },
    }


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def source_record(repo: Path, spec_bytes: bytes) -> dict[str, Any]:
    dirty = bool(git(repo, "status", "--porcelain", "--", str(SOURCE_SPEC)))
    return {
        "repository": SOURCE_REPOSITORY,
        "path": str(SOURCE_SPEC),
        "ref": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": git(repo, "rev-parse", "HEAD"),
        "uncommittedChanges": dirty,
        "sha256": hashlib.sha256(spec_bytes).hexdigest(),
    }


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("apis_repo", type=Path, help="path to a traceport-apis checkout")
    parser.add_argument("--check", action="store_true", help="exit 1 if the snapshot differs from the source")
    args = parser.parse_args()

    spec_path = args.apis_repo / SOURCE_SPEC
    spec_bytes = spec_path.read_bytes()
    contract = render(build_contract(json.loads(spec_bytes), load_allowlist()))

    if args.check:
        current = SNAPSHOT_PATH.read_text() if SNAPSHOT_PATH.exists() else ""
        if current != contract:
            print(f"contract drift: {SNAPSHOT_PATH.relative_to(ROOT)} does not match {spec_path}", file=sys.stderr)
            return 1
        print("contract snapshot is up to date")
        return 0

    record = source_record(args.apis_repo, spec_bytes)
    SNAPSHOT_PATH.write_text(contract)
    SOURCE_PATH.write_text(render(record))
    print(f"wrote {SNAPSHOT_PATH.relative_to(ROOT)} from {record['repository']}@{record['commit'][:12]} ({record['ref']})")
    if record["uncommittedChanges"]:
        print("warning: the source spec has uncommitted changes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
