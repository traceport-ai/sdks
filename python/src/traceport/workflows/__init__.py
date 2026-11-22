"""Traceport workflows product: run saved workflows synchronously or as durable runs.

Takes the shared client from the top-level ``traceport`` package::

    from traceport import Traceport
    from traceport.workflows import Workflows

    workflows = Workflows(Traceport())
    result = workflows.execute(version_id=version_id, input={"question": "Hi"})
"""

from .errors import WaitTimeoutError, WorkflowFailedError
from .result import require_output
from .runs import AsyncRuns, Runs
from .types import (
    TerminalWorkflowRunStatus,
    WorkflowBillingMethod,
    WorkflowResult,
    WorkflowRun,
    WorkflowRunBilling,
    WorkflowRunMode,
    WorkflowRunPage,
    WorkflowRunStatus,
    WorkflowStep,
)
from .workflows import AsyncWorkflows, Workflows

__all__ = [
    "AsyncRuns",
    "AsyncWorkflows",
    "Runs",
    "TerminalWorkflowRunStatus",
    "WaitTimeoutError",
    "WorkflowBillingMethod",
    "WorkflowFailedError",
    "WorkflowResult",
    "WorkflowRun",
    "WorkflowRunBilling",
    "WorkflowRunMode",
    "WorkflowRunPage",
    "WorkflowRunStatus",
    "WorkflowStep",
    "Workflows",
    "require_output",
]
