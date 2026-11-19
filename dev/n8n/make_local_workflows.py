"""Make local copies of the n8n workflows for a Community Edition n8n, which has no Variables feature.

What changes in the copies (the originals in n8n-workflows/ are never touched):
- `$vars.X` becomes `$env.X`. start-n8n-local.ps1 sets those environment variables.
- Each workflow gets the ID it already has in your local n8n (workflow-ids.json), so a re-import updates
  it in place. The Platform error handler is always AmiErrHandler001 and every other workflow points to it.
- Credentials are bound by fixed IDs. credentials.json holds their values for `n8n import:credentials`:
  the API credential uses AUTOMATION_DEV_TOKEN from backend/.env, and the webhook tokens are generated
  once into out/local-secrets.json.

Output goes to dev/n8n/out/, which holds local secrets and is never committed.
"""
import json
import secrets
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "n8n-workflows"
OUT = HERE / "out"
ERROR_HANDLER = ("Platform error handler", "AmiErrHandler001")

API_CREDENTIAL = {"id": "amcPlatformApi01", "name": "Platform API (local)"}
WEBHOOK_CREDENTIALS = {
    "intake": {"id": "amcHookIntake001", "name": "Webhook: intake (local)"},
    "extraction": {"id": "amcHookExtract01", "name": "Webhook: extraction callback (local)"},
    "data-platform": {"id": "amcHookDataPlat1", "name": "Webhook: data platform (local)"},
}
# The README's webhook groups: intake, extraction callback, data-platform events.
WEBHOOK_GROUPS = {
    "bank-statement-received": "intake",
    "nav-statement-received": "intake",
    "transaction-received": "intake",
    "bank-statement-extraction-complete": "extraction",
    "nav-statement-extraction-complete": "extraction",
    "bronze-load-completed": "data-platform",
    "gold-refresh-completed": "data-platform",
}
WEBHOOK_HEADER = "X-Webhook-Token"


def read_dev_token() -> str:
    env_file = ROOT / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("AUTOMATION_DEV_TOKEN=") and line.split("=", 1)[1].strip():
                return line.split("=", 1)[1].strip()
    sys.exit("backend/.env has no AUTOMATION_DEV_TOKEN. Create backend/.env from backend/.env.example first.")


def webhook_tokens() -> dict[str, str]:
    path = OUT / "local-secrets.json"
    if path.exists():
        tokens: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        return tokens
    tokens = {group: secrets.token_urlsafe(32) for group in WEBHOOK_CREDENTIALS}
    path.write_text(json.dumps(tokens, indent=2) + "\n", encoding="utf-8")
    return tokens


def swap_vars(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("$vars.", "$env.")
    if isinstance(value, list):
        return [swap_vars(v) for v in value]
    if isinstance(value, dict):
        return {k: swap_vars(v) for k, v in value.items()}
    return value


def bind_credentials(workflow: dict[str, Any]) -> int:
    bound = 0
    for node in workflow.get("nodes", []):
        params = node.get("parameters", {})
        node_type = node.get("type", "")
        if (
            node_type.endswith("httpRequest")
            and "$env.PLATFORM_API_URL" in str(params.get("url", ""))
            and params.get("genericAuthType") == "httpHeaderAuth"
        ):
            node["credentials"] = {"httpHeaderAuth": dict(API_CREDENTIAL)}
            bound += 1
        elif node_type.endswith(".webhook") and params.get("authentication") == "headerAuth":
            group = WEBHOOK_GROUPS.get(params.get("path", ""))
            if group is None:
                sys.exit(f"Unknown webhook path {params.get('path')!r} in {workflow.get('name')!r}: "
                         "add it to WEBHOOK_GROUPS.")
            node["credentials"] = {"httpHeaderAuth": dict(WEBHOOK_CREDENTIALS[group])}
            bound += 1
    return bound


def main() -> None:
    ids: dict[str, str] = json.loads((HERE / "workflow-ids.json").read_text(encoding="utf-8"))["workflows"]
    out_dir = OUT / "workflows"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()

    for source in sorted(SOURCE.glob("*/*.json")):
        workflow = swap_vars(json.loads(source.read_text(encoding="utf-8")))
        name = workflow["name"]
        if name == ERROR_HANDLER[0]:
            workflow["id"] = ERROR_HANDLER[1]
        else:
            workflow["id"] = ids.get(name) or workflow.get("id")
            workflow.setdefault("settings", {})["errorWorkflow"] = ERROR_HANDLER[1]
        workflow["active"] = False
        bound = bind_credentials(workflow)
        if "$vars." in json.dumps(workflow):
            sys.exit(f"{name}: $vars is still present after the swap")
        (out_dir / f"{source.stem}.json").write_text(
            json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"  {workflow['id'] or '(new ID)':<18} {name}  ({bound} credentials bound)")

    tokens = webhook_tokens()
    credentials = [
        {**API_CREDENTIAL, "type": "httpHeaderAuth",
         "data": {"name": "Authorization", "value": f"Bearer {read_dev_token()}"}},
        *[
            {**WEBHOOK_CREDENTIALS[group], "type": "httpHeaderAuth",
             "data": {"name": WEBHOOK_HEADER, "value": tokens[group]}}
            for group in WEBHOOK_CREDENTIALS
        ],
    ]
    (OUT / "credentials.json").write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(credentials)} credentials written to {OUT / 'credentials.json'}")


if __name__ == "__main__":
    main()
