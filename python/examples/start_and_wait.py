"""Start a durable workflow using a persisted job key, then observe it."""

import os

from traceport_ai import Traceport
from traceport_ai.workflows import WaitTimeoutError, Workflows, require_output


def main() -> None:
    with Traceport() as client:
        workflows = Workflows(client)
        run = workflows.runs.start(
            version_id=os.environ["TRACEPORT_VERSION_ID"],
            input={"question": "Hello"},
            idempotency_key=os.environ["TRACEPORT_JOB_ID"],
        )
        print("started", run.id, run.status)  # Persist run.id with the job.
        try:
            finished = workflows.runs.wait_for_completion(run.id, timeout=120)
        except WaitTimeoutError as error:
            last_status = error.last_run.status if error.last_run else "not yet observed"
            print("observation timed out; read the run later:", error.run_id, last_status)
        else:
            print(require_output(finished))
        page = workflows.runs.list(version_id=run.config_version_id, limit=5)
        print([(item.id, item.status) for item in page.items])


if __name__ == "__main__":
    main()
