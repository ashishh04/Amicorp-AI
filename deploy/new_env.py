"""Create deploy/.env from deploy/.env.example: a fresh value for every secret, and the addresses.

    python3 new_env.py --site 18.232.76.13       the address people will open (a DNS name, or the public IP)
    python3 new_env.py                           secrets only; set the addresses in .env by hand afterwards

With --site it also fills in the addresses when n8n runs on this server: it looks for n8n (a container that
publishes port 5678, or a process listening on it) and uses this server's private address for both directions.
--allow adds public addresses that may open the portal; without it, the address you are connected from is used.

It never overwrites an existing .env: that file's tokens are already in the database and in n8n.
"""
import argparse
import os
import secrets
import sys
from pathlib import Path

import serverinfo as si

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE / ".env.example"
TARGET = HERE / ".env"
API_PORT = 8000

# The password goes inside a database URL, so it is letters and digits only.
GENERATORS = {
    "POSTGRES_PASSWORD": lambda: secrets.token_hex(24),
    "AUTOMATION_DEV_TOKEN": lambda: secrets.token_urlsafe(32),
    "N8N_EXTRACTION_WEBHOOK_TOKEN": lambda: secrets.token_urlsafe(32),
    "N8N_INTAKE_WEBHOOK_TOKEN": lambda: secrets.token_urlsafe(32),
    "N8N_DATA_PLATFORM_WEBHOOK_TOKEN": lambda: secrets.token_urlsafe(32),
}


def n8n_addresses(n8n: si.N8n | None, private: str | None) -> tuple[dict[str, str], str | None]:
    """PLATFORM_API_URL, N8N_WEBHOOK_BASE and API_BIND for an n8n on this server, or a reason why not."""
    if n8n is None:
        return {}, "n8n was not found on this server"
    if private is None:
        return {}, "this server's private address could not be found"
    if n8n.kind == "docker" and n8n.loopback_only:
        return {}, "n8n's port is published on 127.0.0.1 only, so the API's container cannot reach it"
    base = f"http://{private}:{n8n.host_port}"
    if n8n.kind == "docker":
        # Both run in containers: each reaches the other through the server's own address.
        return {"PLATFORM_API_URL": f"http://{private}:{API_PORT}", "N8N_WEBHOOK_BASE": base,
                "API_BIND": "0.0.0.0"}, None  # noqa: S104 - the security group keeps port 8000 closed
    return {"PLATFORM_API_URL": f"http://127.0.0.1:{API_PORT}", "N8N_WEBHOOK_BASE": base, "API_BIND": "127.0.0.1"}, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Create deploy/.env with new secrets and the addresses.")
    parser.add_argument("--site", help="the DNS name or public IP address people will open")
    parser.add_argument("--allow", action="append", default=[], metavar="ADDRESS",
                        help="a public address or range that may open the portal (repeat for more)")
    parser.add_argument("--n8n-url", help="how this server reaches n8n, when n8n is on another server")
    parser.add_argument("--api-url", help="how n8n reaches the Platform API, when n8n is on another server")
    args = parser.parse_args()

    if TARGET.exists():
        sys.exit(f"{TARGET} already exists. It is not overwritten: its tokens are in use. Edit it by hand.")

    values: dict[str, str] = {name: make() for name, make in GENERATORS.items()}
    report: list[str] = []
    todo: list[str] = []
    if args.site:
        values["SITE_ADDRESS"] = args.site.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        allowed = list(args.allow)
        if not allowed:
            client = si.ssh_client_ip()
            if client:
                allowed = [f"{client}/32"]
                report.append(f"{'ALLOWED_IPS':<17} {client}/32  (the address you are connected from)")
            else:
                todo.append("ALLOWED_IPS: your own public address could not be seen. The portal will tell you the "
                            "address to add the first time it refuses you.")
        values["ALLOWED_IPS"] = " ".join(allowed)

        if args.n8n_url or args.api_url:
            if not (args.n8n_url and args.api_url):
                sys.exit("Give --n8n-url and --api-url together.")
            found = {"N8N_WEBHOOK_BASE": args.n8n_url.rstrip("/"), "PLATFORM_API_URL": args.api_url.rstrip("/"),
                     "API_BIND": "0.0.0.0"}  # noqa: S104 - n8n calls from another server
            how = "n8n is on another server (the addresses you gave)"
        else:
            n8n, how = si.find_n8n()
            found, problem = n8n_addresses(n8n, si.private_ip())
            if problem:
                todo.append(f"PLATFORM_API_URL, N8N_WEBHOOK_BASE and API_BIND: {how if n8n is None else problem}. Set them "
                            "by hand (README, step 4), or delete .env and run this again with --n8n-url and --api-url.")
        values.update(found)
        if found:
            report.insert(0, how)
    else:
        todo.append("SITE_ADDRESS, ALLOWED_IPS, PLATFORM_API_URL and N8N_WEBHOOK_BASE (README, step 4).")

    lines, written = [], set()
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        name = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and name in values:
            line = f"{name}={values[name]}"
            written.add(name)
        lines.append(line)
    missing = sorted(set(values) - written)
    if missing:
        sys.exit(f".env.example has no line for: {', '.join(missing)}")
    TARGET.touch(mode=0o600)
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name == "posix":
        TARGET.chmod(0o600)

    print(f"Wrote {TARGET} with {len(GENERATORS)} new secrets.")
    for name in ("SITE_ADDRESS", "PLATFORM_API_URL", "N8N_WEBHOOK_BASE", "API_BIND"):
        if name in values and name not in GENERATORS:
            report.append(f"{name:<17} {values[name]}")
    for text in report:
        print(f"  {text}")
    if todo:
        print("Still to set in .env by hand:")
        for text in todo:
            print(f"  - {text}")


if __name__ == "__main__":
    main()
