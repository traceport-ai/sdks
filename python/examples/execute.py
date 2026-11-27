"""Set TRACEPORT_API_KEY and TRACEPORT_DEPLOYMENT (a deployment code), then run this example."""

import os

from traceport_ai import Traceport
from traceport_ai.workflows import Workflows


def main() -> None:
    # One client serves every Traceport product; each product class takes it.
    with Traceport() as client:
        workflows = Workflows(client)
        result = workflows.execute(
            deployment=os.environ["TRACEPORT_DEPLOYMENT"],
            input={"question": "What is Traceport?"},
        )
        if result.status == "failed":
            print("workflow failed:", result.error, "partial output:", result.output)
        else:
            print(result.output)


if __name__ == "__main__":
    main()
