#!/usr/bin/env python3
"""Record one synthetic HTTP exchange without storing credentials or following redirects."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
RUN_PATH = re.compile(r"/workflow/runs/([^/?]+)")
SAFE_HEADERS = {"content-type", "location", "retry-after"}
ERROR_CLASSES = {
    400: "BadRequestError",
    401: "AuthenticationError",
    402: "PaymentRequiredError",
    403: "PermissionDeniedError",
    404: "NotFoundError",
    409: "ConflictError",
    429: "RateLimitError",
}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def require_safe_request(request: dict) -> None:
    path = request["path"]
    parsed = urlsplit(path)
    if (
        parsed.scheme
        or parsed.netloc
        or not path.startswith("/v1/workflow/")
        or parsed.fragment
    ):
        raise ValueError("request.path must be a relative /v1/workflow/ path")
    if any(name.lower() != "idempotency-key" for name in request.get("headers", {})):
        raise ValueError(
            "request headers may contain only Idempotency-Key; credentials come from the environment"
        )


def prepare_fixture(
    template: dict, exchange: dict, source: dict, *, secrets: tuple = ()
) -> dict:
    """Keep wire values, replace UUIDs/keys consistently, then derive assertions from the recording."""
    require_safe_request(exchange["request"])
    if exchange["response"]["status"] != template["response"]["status"]:
        raise ValueError(
            "recorded status differs from the fixture; inspect the response before updating its contract"
        )
    request, response = (
        copy.deepcopy(exchange["request"]),
        copy.deepcopy(exchange["response"]),
    )
    response["headers"] = {
        name: value
        for name, value in response.get("headers", {}).items()
        if name.lower() in SAFE_HEADERS
    }
    raw = json.dumps({"request": request, "response": response})
    if any(secret and secret in raw for secret in secrets):
        raise ValueError("credential appeared in the exchange; refusing to write it")
    data = response["body"].get("data")
    resource = data if isinstance(data, dict) else {}
    version = (request.get("body") or {}).get("configVersionID")
    version = (
        version
        or parse_qs(urlsplit(request["path"]).query).get("configVersionID", [None])[0]
    )
    version = version or resource.get("configVersionID")
    path_run = RUN_PATH.search(request["path"])
    in_progress = re.search(
        r"original run:\s*(" + UUID.pattern + ")",
        response["body"].get("error", ""),
        re.I,
    )
    run = resource.get("id") or (path_run.group(1) if path_run else None)
    run = run or (in_progress.group(1) if in_progress else None)
    ids = {}
    if version:
        ids[version.lower()] = "00000000-0000-4000-8000-000000000001"
    if run:
        ids[run.lower()] = "00000000-0000-4000-8000-000000000002"
    key = next(iter(request.get("headers", {}).values()), None)
    canonical_key = next(
        iter(template["request"].get("headers", {}).values()), "fixture-key"
    )
    next_id = count(3)

    def replace_id(match):
        value = match.group().lower()
        if value not in ids:
            ids[value] = f"00000000-0000-4000-8000-{next(next_id):012d}"
        return ids[value]

    def sanitize(value):
        if isinstance(value, str):
            value = value.replace(key, canonical_key) if key else value
            return UUID.sub(replace_id, value)
        if isinstance(value, dict):
            return {sanitize(name): sanitize(child) for name, child in value.items()}
        if isinstance(value, list):
            return [sanitize(child) for child in value]
        return value

    request, response = sanitize(request), sanitize(response)
    payload, status = response["body"], response["status"]
    if status >= 400:
        error = {
            "class": ERROR_CLASSES.get(
                status, "InternalServerError" if status >= 500 else "APIError"
            ),
            "status": status,
            "errorCode": payload.get("errorCode", ""),
            "retryable": status in (408, 429, 500, 502, 503, 504),
        }
        if in_progress:
            error["existingRunId"] = ids[in_progress.group(1).lower()]
        expect = {"kind": "error", "error": error}
    else:
        data = payload["data"]
        if template["expect"]["kind"] == "outcome":
            expect = {"kind": "outcome"}
            result = data
        else:
            resource = (
                {
                    "itemCount": len(data["items"]),
                    "limit": data["limit"],
                    "offset": data["offset"],
                }
                if "items" in data
                else {"id": data["id"], "status": data["status"]}
            )
            expect = {"kind": "resource", "resource": resource}
            result = data.get("output")
        if isinstance(result, dict) and isinstance(result.get("data"), dict):
            values, message = result["data"], result.get("error", "")
            final = values.get("final")
            outcome = {
                "status": "failed" if message else "succeeded",
                "output": final if isinstance(final, dict) and final else values,
                "stepCount": len(result.get("steps") or []),
            }
            if message:
                outcome["error"] = message
            expect["outcome"] = outcome
        old_status = template["expect"].get("resource", {}).get("status")
        new_status = expect.get("resource", {}).get("status")
        if old_status and old_status != new_status:
            raise ValueError(
                "run has a different lifecycle status; capture the intended state"
            )
        old_outcome = template["expect"].get("outcome", {}).get("status")
        if old_outcome and old_outcome != expect.get("outcome", {}).get("status"):
            raise ValueError("workflow outcome differs from the intended scenario")
    fixture = {
        name: copy.deepcopy(template[name])
        for name in ("name", "description", "operation")
    }
    fixture.update(
        source={**source, "kind": "recorded"},
        request=request,
        response=response,
        expect=expect,
    )
    if any(secret and secret in json.dumps(fixture) for secret in secrets):
        raise ValueError(
            "credential appeared in fixture metadata; refusing to write it"
        )
    return fixture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture", type=Path, help="existing fixture to replace after review"
    )
    parser.add_argument(
        "--request",
        type=Path,
        required=True,
        help="private JSON request with synthetic values",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="API origin, e.g. http://localhost:1010 (without /v1)",
    )
    parser.add_argument(
        "--source", required=True, help="server build/reference and scenario setup"
    )
    parser.add_argument(
        "--server-spec-sha256",
        required=True,
        help="SHA-256 of that server's /v1/docs/openapi.json",
    )
    args = parser.parse_args()
    origin = urlsplit(args.base_url)
    if (
        origin.scheme not in ("http", "https")
        or not origin.netloc
        or origin.path not in ("", "/")
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
    ):
        parser.error(
            "--base-url must be an HTTP(S) origin without credentials, path, query or fragment"
        )
    if not re.fullmatch(r"[0-9a-f]{64}", args.server_spec_sha256):
        parser.error("--server-spec-sha256 must be a lowercase SHA-256 digest")
    key = os.environ.get("TRACEPORT_API_KEY")
    if not key:
        parser.error("set TRACEPORT_API_KEY; it is never stored in the fixture")
    template, request = (
        json.loads(args.fixture.read_text()),
        json.loads(args.request.read_text()),
    )
    require_safe_request(request)
    headers = {
        **request.get("headers", {}),
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
    }
    body = json.dumps(request["body"]).encode() if "body" in request else None
    http = Request(
        args.base_url.rstrip("/") + request["path"],
        data=body,
        headers=headers,
        method=request["method"],
    )
    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        response = build_opener(NoRedirects()).open(http, timeout=60)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("response exceeds the recording limit")
        exchange = {
            "request": request,
            "response": {
                "status": response.code,
                "headers": dict(response.headers),
                "body": json.loads(raw),
            },
        }
    fixture = prepare_fixture(
        template,
        exchange,
        {
            "from": args.source,
            "recordedAt": recorded_at,
            "capture": "live-http",
            "serverSpecSha256": args.server_spec_sha256,
        },
        secrets=(key,),
    )
    args.fixture.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
    print(f"Recorded {fixture['name']}; inspect the sanitized diff before committing.")


if __name__ == "__main__":
    main()
