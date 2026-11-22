from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, overload

from pydantic import ValidationError

from .._core.errors import InvalidResponseError
from .errors import WorkflowFailedError
from .types import WorkflowResult, WorkflowRun, WorkflowRunPage, WorkflowStep

_T = TypeVar("_T")


def parse_result(value: Any, status: int = 200) -> WorkflowResult:
    if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
        raise InvalidResponseError(
            "response does not contain a workflow result", status=status, body=value
        )
    data = value["data"]
    error = value.get("error", "")
    if not isinstance(error, str):
        raise InvalidResponseError("workflow error must be a string", status=status, body=value)
    error = error.strip()
    final = data.get("final")
    output = final if isinstance(final, dict) and final else data
    steps = value.get("steps")
    if steps is None:
        steps = []
    try:
        return WorkflowResult(
            status="failed" if error else "succeeded",
            output=output,
            error=error or None,
            data=data,
            steps=[WorkflowStep.model_validate(step) for step in steps],
        )
    except (ValidationError, TypeError) as exc:
        raise InvalidResponseError("invalid workflow steps", status=status, body=value) from exc


def parse_run(value: Any, status: int = 200) -> WorkflowRun:
    required = {"id", "configVersionID", "revision", "status", "mode", "source", "createdAt"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise InvalidResponseError("response is not a workflow run", status=status, body=value)
    wire = dict(value)
    wire.pop("result", None)  # result is SDK-derived, not a trusted wire field.
    try:
        run = WorkflowRun.model_validate(wire)
    except ValidationError as exc:
        raise InvalidResponseError(
            "response is not a workflow run", status=status, body=value
        ) from exc
    if run.output is not None:
        try:
            run.result = parse_result(run.output, status)
        except InvalidResponseError:
            pass  # Keep unrecognized stored output readable without an interpreted result.
    return run


def parse_page(value: Any, status: int) -> WorkflowRunPage:
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise InvalidResponseError("response is not a run page", status=status, body=value)
    items = [parse_run(item, status) for item in value["items"]]
    try:
        return WorkflowRunPage.model_validate({**value, "items": items})
    except ValidationError as exc:
        raise InvalidResponseError("response is not a run page", status=status, body=value) from exc


@overload
def require_output(target: WorkflowResult | WorkflowRun, decode: Callable[[Any], _T]) -> _T: ...


@overload
def require_output(target: WorkflowResult | WorkflowRun, decode: None = None) -> Any: ...


def require_output(
    target: WorkflowResult | WorkflowRun, decode: Callable[[Any], _T] | None = None
) -> Any:
    """Return successful output or raise WorkflowFailedError retaining partial results."""
    result = target if isinstance(target, WorkflowResult) else target.result
    if target.status == "succeeded" and result is not None and result.status == "succeeded":
        return decode(result.output) if decode is not None else result.output
    if isinstance(target, WorkflowResult):
        raise WorkflowFailedError(target.error or "workflow failed", status="failed", result=target)
    message = target.error or (result.error if result else None)
    if not message:
        message = (
            f"run {target.id} has no output; read it with runs.get"
            if target.status == "succeeded"
            else f"run {target.id} is {target.status}"
        )
    raise WorkflowFailedError(message, run_id=target.id, status=target.status, result=result)
