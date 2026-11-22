from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

WorkflowRunStatus = Literal["queued", "running", "succeeded", "failed", "interrupted"]
TerminalWorkflowRunStatus = Literal["succeeded", "failed", "interrupted"]
WorkflowRunMode = Literal["production", "draft_test"]
WorkflowBillingMethod = Literal["included", "wallet", "invoice"]
_T = TypeVar("_T")


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, strict=True)


class WorkflowRunBilling(_Model):
    """First-processing billing receipt, retaining decimal amounts as strings."""

    method: WorkflowBillingMethod
    period_month: str = Field(alias="periodMonth")
    currency: Literal["USD"]
    amount_usd: str = Field(alias="amountUsd")
    credited_at: datetime | None = Field(default=None, alias="creditedAt", strict=False)


class WorkflowStep(_Model):
    """One executed node. model_extra retains additive usage, branch and tool fields."""

    index: int
    node_id: str = Field(alias="nodeId")
    name: str
    type: str
    attempt: int
    status: str
    started_at: datetime | None = Field(default=None, alias="startedAt", strict=False)
    duration_ms: float = Field(alias="durationMs")
    input: dict[str, Any] | None = None
    output: Any = None
    error: str | None = None


class WorkflowResult(_Model):
    """Interpreted workflow outcome, including partial output from failed executions."""

    status: Literal["succeeded", "failed"]
    output: Any
    error: str | None = None
    data: dict[str, Any]
    steps: list[WorkflowStep] = Field(default_factory=list)

    def require_output(self, decode: Callable[[Any], _T] | None = None) -> Any:
        from .result import require_output

        return require_output(self, decode)


class WorkflowRun(_Model):
    """Durable run. Summaries omit output/result; use runs.get to read stored output."""

    id: str = Field(min_length=1)
    config_version_id: str = Field(alias="configVersionID", min_length=1)
    revision: int = Field(ge=0)
    status: WorkflowRunStatus
    mode: WorkflowRunMode
    source: str
    created_at: datetime = Field(alias="createdAt", strict=False)
    started_at: datetime | None = Field(default=None, alias="startedAt", strict=False)
    finished_at: datetime | None = Field(default=None, alias="finishedAt", strict=False)
    error: str | None = None
    failure_origin: str | None = Field(default=None, alias="failureOrigin")
    billing: WorkflowRunBilling | None = None
    output: dict[str, Any] | None = None
    result: WorkflowResult | None = Field(default=None, exclude=True)

    @field_validator("id", "config_version_id")
    @classmethod
    def _nonempty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resource IDs must not be empty")
        return value

    @field_validator("created_at", "started_at", "finished_at", mode="before")
    @classmethod
    def _timestamp(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("timestamps must be ISO 8601 strings")
        return value

    def require_output(self, decode: Callable[[Any], _T] | None = None) -> Any:
        from .result import require_output

        return require_output(self, decode)


class WorkflowRunPage(_Model):
    """One page of newest-first run summaries. There is no total-count guarantee."""

    items: list[WorkflowRun]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
