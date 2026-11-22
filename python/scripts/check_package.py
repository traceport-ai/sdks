"""Inspect a wheel and smoke-test its installed sync/async API outside the source tree."""

from __future__ import annotations

import argparse
import email
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SMOKE = """
import asyncio
from importlib.metadata import version
from pathlib import Path
import httpx
import traceport
from traceport.workflows import AsyncWorkflows, Workflows, require_output

assert "/src/traceport/" not in str(Path(traceport.__file__).resolve())
assert traceport.__version__ == version("traceport")

def handler(request):
    assert request.headers["authorization"] == "Bearer smoke-key"
    assert request.headers["idempotency-key"]
    return httpx.Response(200, json={"data": {"data": {"final": {"ok": True}}, "error": "", "steps": []}, "error": "", "status": 200, "errorCode": ""})

with httpx.Client(transport=httpx.MockTransport(handler)) as http:
    with traceport.Traceport(api_key="smoke-key", http_client=http) as sdk:
        workflows = Workflows(sdk)
        assert workflows.execute(version_id="test-version").require_output() == {"ok": True}
        # A derived client shares the connection pool and products still accept it.
        derived = Workflows(sdk.with_options(timeout=5))
        assert derived.execute(version_id="test-version").require_output() == {"ok": True}
    assert not http.is_closed

async def main():
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with traceport.AsyncTraceport(api_key="smoke-key", http_client=http) as sdk:
            result = await AsyncWorkflows(sdk).execute(version_id="test-version")
            assert require_output(result) == {"ok": True}
        assert not http.is_closed

asyncio.run(main())
print("Installed wheel: sync and async consumer checks passed")
"""


def check(wheel: Path, uv: str, offline: bool) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for required in (
            "traceport/__init__.py",
            "traceport/py.typed",
            "traceport/_core/transport.py",
            "traceport/workflows/__init__.py",
            "traceport/workflows/runs.py",
            "traceport/workflows/types.py",
        ):
            assert required in names, f"wheel is missing {required}"
        assert not any(name.startswith(("tests/", "examples/", ".venv/")) for name in names)
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(archive.read(metadata_name))
        assert metadata["License-Expression"] == "Apache-2.0"
        assert any(name.endswith("/licenses/LICENSE") for name in names)
        dependencies = {
            re.match(r"[\w-]+", requirement).group(0).lower()
            for requirement in metadata.get_all("Requires-Dist", [])
            if "extra ==" not in requirement
        }
        assert dependencies == {"httpx", "pydantic"}, dependencies
    with tempfile.TemporaryDirectory(prefix="traceport-wheel-") as temp:
        root = Path(temp)
        environment = root / "venv"
        subprocess.run([uv, "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [uv, "pip", "install", "--python", str(python), str(wheel.resolve())]
        if offline:
            install.append("--offline")
        subprocess.run(install, check=True)
        consumer = root / "consumer.py"
        consumer.write_text(SMOKE)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        subprocess.run([str(python), str(consumer)], cwd=root, env=env, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    check(args.wheel, args.uv, args.offline)
