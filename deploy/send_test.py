"""Send one test bank statement through n8n and watch for its work card: the end-to-end check.

    python3 send_test.py

It calls n8n's intake webhook the way the intake system would (with the token from .env), then asks the
Platform API until the validation card for that statement exists. It prints PASSED or what to look at.
The statement is synthetic: the extractor stand-in always returns the same sample HSBC statement.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import serverinfo as si

HERE = Path(__file__).resolve().parent
WAIT_SECONDS = 120


def call(method: str, url: str, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,  # noqa: S310 - this deployment's own addresses
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310
            status, raw = answer.status, answer.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw.decode("utf-8", "replace")[:300]


def stop(message: str) -> None:
    print(f"\nFAILED: {message}")
    sys.exit(1)


def main() -> None:
    if not (HERE / ".env").exists():
        stop("There is no .env in this folder yet, so nothing has been deployed here. "
             "Run:  python3 deploy.py --site <the server's public IP>")
    env = si.read_env(HERE / ".env")
    n8n = env.get("N8N_WEBHOOK_BASE", "").rstrip("/")
    token = env.get("N8N_INTAKE_WEBHOOK_TOKEN", "")
    api = f"http://127.0.0.1:{env.get('API_PORT') or 8000}"
    if not n8n or not token:
        empty = " and ".join(name for name, value in (("N8N_WEBHOOK_BASE", n8n), ("N8N_INTAKE_WEBHOOK_TOKEN", token)) if not value)
        stop(f"{empty} is empty in .env: the settings step did not finish, so the steps after it could not work "
             "either. Run:  python3 deploy.py --site <the server's public IP>   It completes .env and does the rest.")

    now = datetime.now(UTC)
    statement = {"channel": "email", "objectKey": f"raw-docs/uc1/{now:%Y/%m}/hsbc-test-{int(time.time())}.pdf",
                 "receivedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    api_for_n8n = env.get("PLATFORM_API_URL", "")
    blocked = (f"n8n cannot reach the Platform API at {api_for_n8n}. If n8n is on another server, open port 8000 of "
               "this server to the n8n server's address in the cloud firewall (AWS: this server's security group). "
               "The failed execution in the n8n editor (Executions) shows the error.")
    print(f"1. Sending a bank statement to n8n at {n8n} ...")
    target = urllib.parse.urlsplit(n8n)
    if not si.port_open(target.hostname or "", target.port or (443 if target.scheme == "https" else 80), timeout=6):
        stop(f"This server cannot connect to n8n at {n8n}. Is n8n running? If it is on another server, open its port to "
             "this server's address in the cloud firewall.")
    try:
        status, answer = call("POST", f"{n8n}/webhook/bank-statement-received", statement, {"X-Webhook-Token": token})
    except OSError as error:
        if "timed out" in str(error).lower():  # n8n took the request and is still trying to call the API
            stop(f"n8n took the statement but did not answer within 30 seconds. {blocked}")
        stop(f"n8n cannot be reached at {n8n} ({error}). Is n8n running, and is N8N_WEBHOOK_BASE right?")
    if status == 404:
        stop("n8n does not know the webhook: the workflows are not published, or n8n is still starting. "
             "Run:  python3 deploy.py")
    if status == 403:
        stop("n8n refused the token: its credentials are older than .env. Run:  python3 deploy.py")
    if status >= 300 or not isinstance(answer, dict) or not answer.get("statementId"):
        stop(f"n8n answered HTTP {status}: {answer}\n  n8n reached the workflow but could not register the statement. "
             f"{blocked} Also look at:  docker compose logs --tail 40 api")
    statement_id = answer["statementId"]
    print(f"   accepted, statement {statement_id}")

    print("2. Waiting for the Platform API to extract it, call n8n back, and create the card ...")
    try:
        status, users = call("GET", f"{api}/v1/dev/users")
    except OSError as error:
        stop(f"The Platform API cannot be reached at {api} ({error}). Check:  docker compose ps")
    people = users.get("items", []) if isinstance(users, dict) else []
    officer = next((p for p in people if "Operations" in p.get("teams", [])), None)
    if officer is None:
        stop("The sample officers are missing. Run:  docker compose exec api python -m scripts.seed")
    status, session = call("POST", f"{api}/v1/dev/sign-in", {"userId": officer["id"]})
    if status != 200:
        stop(f"The Platform API refused the sample sign-in (HTTP {status}).")
    bearer = {"Authorization": f"Bearer {session['accessToken']}"}

    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        status, page = call("GET", f"{api}/v1/cards?view=team&limit=100", headers=bearer)
        cards = page.get("items", []) if isinstance(page, dict) else []
        card = next((c for c in cards if c.get("subjectId") == statement_id), None)
        if card:
            owner = (card.get("owner") or {}).get("name", "the Operations team")
            print(f"   card created: {card.get('title')}")
            print(f"   state {card.get('state')}, owner {owner}")
            print("\nPASSED: n8n and the Platform API work together in both directions.")
            print(f"Open the portal, sign in as {owner} (or Chan Tai Man), and the card is there.")
            return
        time.sleep(3)
    stop(f"The statement was accepted, but no card appeared within {WAIT_SECONDS} seconds. The Platform API probably "
         "cannot call n8n back at N8N_WEBHOOK_BASE. Look at:  docker compose logs --tail 60 api | grep -i -E 'callback|error'")


if __name__ == "__main__":
    main()
