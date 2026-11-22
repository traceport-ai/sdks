from collections.abc import Mapping
from threading import Event
from typing import TypedDict


class RequestOptions(TypedDict, total=False):
    """Per-request settings. Timeout is measured in seconds and applies per attempt."""

    timeout: float
    max_retries: int
    headers: Mapping[str, str]
    cancel_event: Event
