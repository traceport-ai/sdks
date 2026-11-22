import json
from urllib.parse import parse_qsl

import pytest

import traceport

from .helpers import fixtures


@pytest.mark.parametrize("fixture", fixtures(), ids=lambda fixture: fixture["name"])
async def test_shared_fixture(make, fixture):
    reply = fixture["response"]
    h = make([traceport_http_response(reply)])
    expected = fixture["expect"]
    params = fixture["request"].get("body", {})
    key = fixture["request"].get("headers", {}).get("Idempotency-Key")
    options = {"idempotency_key": key} if key else {}
    url = fixture["request"]["path"]
    operation = fixture["operation"]

    async def invoke():
        if operation == "executeWorkflow":
            return await h.call(
                h.workflows.execute,
                version_id=params["configVersionID"],
                input=params.get("additional"),
                **options,
            )
        if operation == "startWorkflowRun":
            return await h.call(
                h.workflows.runs.start,
                version_id=params["configVersionID"],
                input=params.get("additional"),
                **options,
            )
        if operation == "getWorkflowRun":
            return await h.call(h.workflows.runs.get, url.rsplit("/", 1)[-1])
        query = dict(parse_qsl(url.partition("?")[2]))
        filters = {}
        for wire, name in (
            ("configVersionID", "version_id"),
            ("status", "status"),
            ("limit", "limit"),
            ("offset", "offset"),
        ):
            if wire in query:
                filters[name] = int(query[wire]) if wire in {"limit", "offset"} else query[wire]
        return await h.call(h.workflows.runs.list, **filters)

    if expected["kind"] == "error":
        spec = expected["error"]
        with pytest.raises(getattr(traceport, spec["class"])) as caught:
            await invoke()
        error = caught.value
        assert isinstance(error, traceport.APIError)
        assert error.status == spec["status"]
        assert error.error_code == spec["errorCode"]
        assert error.retryable == spec["retryable"]
        if "existingRunId" in spec:
            assert error.existing_run_id == spec["existingRunId"]
    else:
        value = await invoke()
        if expected.get("outcome"):
            outcome = value if expected["kind"] == "outcome" else value.result
            spec = expected["outcome"]
            assert outcome.status == spec["status"]
            assert outcome.output == spec["output"]
            assert outcome.error == spec.get("error")
            if "stepCount" in spec:
                assert len(outcome.steps) == spec["stepCount"]
        resource = expected.get("resource", {})
        if "itemCount" in resource:
            assert len(value.items) == resource["itemCount"]
            assert value.limit == resource["limit"]
            assert value.offset == resource["offset"]
            assert all(item.output is None and item.result is None for item in value.items)
        else:
            wire = value.model_dump(mode="json", by_alias=True)
            for field, item in resource.items():
                assert wire[field] == item

    assert len(h.requests) == 1
    request = h.requests[0]
    assert request.method == fixture["request"]["method"]
    assert request.url.path == url.partition("?")[0]
    assert dict(request.url.params) == dict(parse_qsl(url.partition("?")[2]))
    assert (json.loads(request.content) if request.content else None) == fixture["request"].get(
        "body"
    )
    assert request.headers["authorization"] == "Bearer test-key"
    for name, value in fixture["request"].get("headers", {}).items():
        assert request.headers[name] == value


def traceport_http_response(reply):
    import httpx

    return httpx.Response(reply["status"], json=reply["body"], headers=reply.get("headers"))
