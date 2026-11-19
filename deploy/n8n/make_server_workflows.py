"""Make the copies of the n8n workflows and their credentials for the server's n8n.

    python3 n8n/make_server_workflows.py          (from the deploy folder, after .env exists)

It writes deploy/n8n/out/, which n8n/import_to_n8n.py then loads into n8n (deploy/README.md, step 7):
- workflows/*.json   the seven workflows, with a fixed ID each, bound to the credentials and to the Platform
                     error handler. n8n Community Edition has no Variables, so every `$vars.X` is replaced by
                     its value from deploy/.env, written into the copy. Nothing has to be changed in n8n's own
                     settings, and n8n is only restarted, never created again.
- credentials.json   four Header Auth credentials, with the tokens from deploy/.env.

Run it again, and import again, whenever an address or a token in .env changes or a workflow file changes.
The originals in n8n-workflows/ are never changed. The binding of credentials is the code of
dev/n8n/make_local_workflows.py, so local and server copies cannot drift apart.
out/ holds tokens in plain text: do not commit or share it.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEPLOY = HERE.parent
ROOT = DEPLOY.parent
OUT = HERE / "out"
ENV_FILE = DEPLOY / ".env"

sys.path.insert(0, str(ROOT / "dev" / "n8n"))
sys.path.insert(0, str(DEPLOY))
import make_local_workflows as local  # noqa: E402 - needs the paths above
import serverinfo as si  # noqa: E402

MIN_TOKEN_LENGTH = 32
API_TOKEN = "AUTOMATION_DEV_TOKEN"
WEBHOOK_TOKENS = {  # webhook group (make_local_workflows.WEBHOOK_CREDENTIALS) -> setting in deploy/.env
    "intake": "N8N_INTAKE_WEBHOOK_TOKEN",
    "extraction": "N8N_EXTRACTION_WEBHOOK_TOKEN",
    "data-platform": "N8N_DATA_PLATFORM_WEBHOOK_TOKEN",
}
URLS = ("PLATFORM_API_URL", "N8N_WEBHOOK_BASE")
# The other workflow variables (n8n-workflows/README.md) and their defaults; a line in .env overrides one.
DEFAULTS = {
    "OPS_ALERT_WEBHOOK_URL": "",       # Teams fallback alert, used only when the Platform API cannot be reached
    "UC4_MAX_NEW_CARDS_PER_RUN": "200",
    "UC5_MAX_NEW_CARDS_PER_RUN": "200",
    "REDRIVE_AFTER_MINUTES": "30",
    "REDRIVE_MAX_ATTEMPTS": "3",
}
VARIABLE = re.compile(r"\$env\.([A-Za-z0-9_]+)")
UNSAFE = re.compile(r"['\"\\{}\s]")   # would end the quoted value or the n8n expression around it


def checked(env: dict[str, str]) -> dict[str, str]:
    problems = []
    for name in (API_TOKEN, *WEBHOOK_TOKENS.values()):
        if len(env.get(name, "")) < MIN_TOKEN_LENGTH:
            problems.append(f"{name} is missing or shorter than {MIN_TOKEN_LENGTH} characters (python3 new_env.py makes it)")
    for name in URLS:
        value = env.get(name, "").rstrip("/")
        if not value.startswith(("http://", "https://")):
            problems.append(f"{name} must be an address that starts with http:// or https://")
        env[name] = value  # a path is joined to it, so no "/" at the end
    for name, default in DEFAULTS.items():
        env[name] = env.get(name, default)
    for name in (*URLS, *DEFAULTS):
        if UNSAFE.search(env[name]):
            problems.append(f"{name} must not contain quotes, spaces, braces or backslashes")
    if problems:
        sys.exit(f"{ENV_FILE}:\n  " + "\n  ".join(problems))
    return env


def write_in_values(value: Any, env: dict[str, str]) -> Any:
    """Replace every `$env.NAME` in the workflow's expressions by the value itself, as a quoted text."""
    if isinstance(value, str):
        def literal(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in env or name not in (*URLS, *DEFAULTS):
                sys.exit(f"A workflow uses the variable {name}, which this script does not know: add it to DEFAULTS.")
            return "'" + env[name] + "'"
        return VARIABLE.sub(literal, value)
    if isinstance(value, list):
        return [write_in_values(v, env) for v in value]
    if isinstance(value, dict):
        return {k: write_in_values(v, env) for k, v in value.items()}
    return value


def server_name(name: str) -> str:
    return name.replace("(local)", "(server)")


def rename_credentials(workflow: dict[str, Any]) -> None:
    for node in workflow.get("nodes", []):
        for credential in node.get("credentials", {}).values():
            credential["name"] = server_name(credential["name"])


def main() -> None:
    if not ENV_FILE.exists():
        sys.exit(f"{ENV_FILE} does not exist. Create it first:  python3 new_env.py --site <address>")
    env = checked(si.read_env(ENV_FILE))
    ids: dict[str, str] = json.loads((local.HERE / "workflow-ids.json").read_text(encoding="utf-8"))["workflows"]

    workflow_dir = OUT / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    for old in workflow_dir.glob("*.json"):
        old.unlink()
    (OUT / "n8n.env").unlink(missing_ok=True)  # written by an earlier version; no longer used

    handler_name, handler_id = local.ERROR_HANDLER
    print("Workflows:")
    for source in sorted(local.SOURCE.glob("*/*.json")):
        workflow = local.swap_vars(json.loads(source.read_text(encoding="utf-8")))
        name = workflow["name"]
        if name == handler_name:
            workflow["id"] = handler_id
        else:
            if name not in ids:
                sys.exit(f"{name!r} has no ID in dev/n8n/workflow-ids.json: add one (16 letters and digits).")
            workflow["id"] = ids[name]
            workflow.setdefault("settings", {})["errorWorkflow"] = handler_id
        workflow["active"] = False
        bound = local.bind_credentials(workflow)  # recognises the API nodes by `$env.PLATFORM_API_URL`
        rename_credentials(workflow)
        workflow = write_in_values(workflow, env)
        left = re.findall(r"\$(?:vars|env)\.\w+", json.dumps(workflow))
        if left:
            sys.exit(f"{name}: still refers to {sorted(set(left))}")
        (workflow_dir / f"{source.stem}.json").write_text(
            json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"  {workflow['id']:<18} {name}  ({bound} credentials bound)")

    credentials = [
        {**local.API_CREDENTIAL, "name": server_name(local.API_CREDENTIAL["name"]), "type": "httpHeaderAuth",
         "data": {"name": "Authorization", "value": f"Bearer {env[API_TOKEN]}"}},
        *[
            {**local.WEBHOOK_CREDENTIALS[group], "name": server_name(local.WEBHOOK_CREDENTIALS[group]["name"]),
             "type": "httpHeaderAuth", "data": {"name": local.WEBHOOK_HEADER, "value": env[setting]}}
            for group, setting in WEBHOOK_TOKENS.items()
        ],
    ]
    credentials_file = OUT / "credentials.json"
    credentials_file.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
    if os.name == "posix":
        OUT.chmod(0o700)
        credentials_file.chmod(0o600)

    print(f"Credentials: {len(credentials)} in {credentials_file}")
    print(f"  n8n calls the Platform API at   {env['PLATFORM_API_URL']}")
    print(f"  the Platform API calls n8n at   {env['N8N_WEBHOOK_BASE']}")
    print("Next: load them into n8n:  python3 n8n/import_to_n8n.py")


if __name__ == "__main__":
    main()
