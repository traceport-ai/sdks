"""AsyncIO execution. These are real workflow calls when explicitly run."""

import asyncio
import os

from traceport_ai import AsyncTraceport
from traceport_ai.workflows import AsyncWorkflows


async def main() -> None:
    async with AsyncTraceport() as client:
        workflows = AsyncWorkflows(client)
        result = await workflows.execute(
            deployment=os.environ["TRACEPORT_DEPLOYMENT"],
            input={"question": "What is Traceport?"},
        )
        print(result.status, result.output, result.error)


if __name__ == "__main__":
    asyncio.run(main())
