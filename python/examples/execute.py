"""Set TRACEPORT_API_KEY and TRACEPORT_VERSION_ID, then run this example."""

import os

from traceport import Traceport
from traceport.workflows import Workflows


def main() -> None:
    # One client serves every Traceport product; each product class takes it.
    with Traceport() as client:
        workflows = Workflows(client)
        result = workflows.execute(
            version_id=os.environ["TRACEPORT_VERSION_ID"],
            input={"question": "What is Traceport?"},
        )
        if result.status == "failed":
            print("workflow failed:", result.error, "partial output:", result.output)
        else:
            print(result.output)


if __name__ == "__main__":
    main()
