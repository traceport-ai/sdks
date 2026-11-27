import json
from importlib.metadata import version
from typing import get_args

from traceport_ai import __version__
from traceport_ai.workflows import (
    WorkflowBillingMethod,
    WorkflowRun,
    WorkflowRunBilling,
    WorkflowRunMode,
    WorkflowRunStatus,
)

from .helpers import REPO


def test_models_match_shared_contract():
    schemas = json.loads((REPO / "contract/openapi.json").read_text())["components"]["schemas"]
    for name, model in (("WorkflowRun", WorkflowRun), ("WorkflowRunBilling", WorkflowRunBilling)):
        fields = {
            field.alias or name for name, field in model.model_fields.items() if name != "result"
        }
        assert fields == set(schemas[name]["properties"])
        required = {
            field.alias or name for name, field in model.model_fields.items() if field.is_required()
        }
        assert required == set(schemas[name]["required"])
    assert set(get_args(WorkflowRunStatus)) == set(
        schemas["WorkflowRun"]["properties"]["status"]["enum"]
    )
    assert set(get_args(WorkflowRunMode)) == set(
        schemas["WorkflowRun"]["properties"]["mode"]["enum"]
    )
    assert set(get_args(WorkflowBillingMethod)) == set(
        schemas["WorkflowRunBilling"]["properties"]["method"]["enum"]
    )


def test_version_matches_installed_distribution():
    assert __version__ == version("traceport-ai")
