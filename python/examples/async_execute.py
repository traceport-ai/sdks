"""AsyncIO execution. These are real workflow calls when explicitly run."""

import asyncio
import os

from traceport import AsyncTraceport
from traceport.workflows import AsyncWorkflows


async def main() -> None:
    async with AsyncTraceport() as client:
        workflows = AsyncWorkflows(client)
        result = await workflows.execute(
            version_id=os.environ["TRACEPORT_VERSION_ID"],
            input={"question": "What is Traceport?"},
        )
        print(result.status, result.output, result.error)


if __name__ == "__main__":
    asyncio.run(main())
