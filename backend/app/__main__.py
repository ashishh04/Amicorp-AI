"""Run the API locally: `python -m app` (port 8000, auto-reload).

Uses asyncio's SelectorEventLoop, which psycopg's async mode needs on Windows.
API_PORT and API_RELOAD override the defaults (a generic PORT variable is often set by other tools).
"""
import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("API_PORT", "8000")),
        reload=os.environ.get("API_RELOAD", "true").lower() == "true",
        loop="asyncio:SelectorEventLoop",
        access_log=False,  # the middleware writes one structured line per request
        server_header=False,
    )


if __name__ == "__main__":
    main()
