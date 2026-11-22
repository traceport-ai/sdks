from __future__ import annotations

from typing import TYPE_CHECKING

from .._core.errors import TraceportError

if TYPE_CHECKING:
    from .types import WorkflowResult, WorkflowRun


class WorkflowFailedError(TraceportError):
    """Opt-in failure from require_output, retaining any partial workflow result."""

    def __init__(
        self,
        message: str,
        *,
        status: str,
        result: WorkflowResult | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.result = result
        self.run_id = run_id


class WaitTimeoutError(TraceportError):
    """Observation expired; the accepted server-side run keeps going."""

    def __init__(self, run_id: str, last_run: WorkflowRun | None, timeout: float) -> None:
        detail = f"last status: {last_run.status}" if last_run else "no status received"
        super().__init__(f"run {run_id} did not finish within {timeout} seconds ({detail})")
        self.run_id = run_id
        self.last_run = last_run
        self.timeout = timeout
