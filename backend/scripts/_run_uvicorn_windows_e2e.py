"""Windows-only local E2E launcher: psycopg's async driver needs a selector
event loop, which Windows does not default to. Docker/Linux (the real
deployment target) is unaffected - this file exists only for local manual
browser E2E verification and is not part of the shipped application."""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000)
