"""Create or complete deploy/.env: a value for every secret, and the addresses.

    python3 new_env.py --site 203.0.113.10       the address people will open (a DNS name, or the public IP)
    python3 new_env.py                           secrets only; set the addresses in .env by hand afterwards

The first run copies .env.example and fills it in. A later run completes the same file and is safe to repeat:
it never replaces a secret or an n8n address that is already set, because the database and n8n use them.
Only SITE_ADDRESS follows --site, so a changed public IP is one command.

With n8n on this server it fills in the addresses itself: if n8n answers on this server's own (private)
address, the Platform API's container can call it there, and n8n can call the API on the same address.
--allow adds public addresses that may open the portal; if none is set, the address you are connected from is used.
deploy.py runs this for you.
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
ADDRESSES = ("SITE_ADDRESS", "ALLOWED_IPS", "PLATFORM_API_URL", "N8N_WEBHOOK_BASE", "API_BIND")
REQUIRED = ("SITE_ADDRESS", "PLATFORM_API_URL", "N8N_WEBHOOK_BASE")

# The password goes inside a database URL, so it is letters and digits only.
GENERATORS = {
    "POSTGRES_PASSWORD": lambda: secrets.token_hex(24),
    "AUTOMATION_DEV_TOKEN": lambda: secrets.token_urlsafe(32),
    "N8N_EXTRACTION_WEBHOOK_TOKEN": lambda: secrets.token_urlsafe(32),
    "N8N_INTAKE_WEBHOOK_TOKEN": lambda: secrets.token_urlsafe(32),
    "N8N_DATA_PLATFORM_WEBHOOK_TOKEN": lambda: secrets.token_urlsafe(32),
}


def n8n_addresses(n8n: si.N8n | None, private: str | None) -> tuple[dict[str, str], str | None]:
    """PLATFORM_API_URL, N8N_WEBHOOK_BASE and API_BIND for an n8n on this server, or the reason why not.
    The same three values serve an n8n in a container and an n8n that runs as a program."""
    if n8n is None:
        return {}, "n8n was not found on this server"
    if private is None:
        return {}, "this server's private address could not be found"
    if n8n.loopback_only:
        return {}, "n8n answers on 127.0.0.1 only, so the API's container cannot reach it"
    return {"PLATFORM_API_URL": f"http://{private}:{API_PORT}", "N8N_WEBHOOK_BASE": f"http://{private}:{n8n.host_port}",
            "API_BIND": "0.0.0.0"}, None  # noqa: S104 - the cloud firewall keeps port 8000 closed to the outside


def complete(site: str | None = None, allow: list[str] | None = None, n8n_url: str | None = None,
             api_url: str | None = None) -> tuple[list[str], list[str]]:
    """Create .env, or complete the one that exists. Returns (what it did, what is still missing)."""
    created = not TARGET.exists()
    lines = (EXAMPLE if created else TARGET).read_text(encoding="utf-8").splitlines()
    current = {} if created else si.read_env(TARGET)
    want: dict[str, str] = {}
    report: list[str] = [f"{'Created' if created else 'Completed'} {TARGET}"]

    new_secrets = [name for name in GENERATORS if not current.get(name)]
    want.update({name: GENERATORS[name]() for name in new_secrets})
    report.append(f"secrets: {len(new_secrets)} new, {len(GENERATORS) - len(new_secrets)} kept")

    if site:
        want["SITE_ADDRESS"] = site.strip().removeprefix("https://").removeprefix("http://").rstrip("/")

    allowed = current.get("ALLOWED_IPS", "").split()
    before = list(allowed)
    allowed += [a for a in (allow or []) if a not in allowed]
    if not allowed:
        client = si.ssh_client_ip()
        if client:
            allowed = [f"{client}/32"]
            report.append(f"allowed the address you are connected from ({client}) to open the portal")
    if allowed != before:
        want["ALLOWED_IPS"] = " ".join(allowed)

    if n8n_url or api_url:
        if not (n8n_url and api_url):
            sys.exit("Give --n8n-url and --api-url together.")
        want.update({"N8N_WEBHOOK_BASE": n8n_url.rstrip("/"), "PLATFORM_API_URL": api_url.rstrip("/"),
                     "API_BIND": "0.0.0.0"})  # noqa: S104 - n8n calls from another server
        report.append("n8n is on another server (the addresses you gave)")
    elif not (current.get("PLATFORM_API_URL") and current.get("N8N_WEBHOOK_BASE")):
        n8n, how = si.find_n8n()
        found, problem = n8n_addresses(n8n, si.private_ip())
        want.update(found)
        report.append(how if n8n is not None else f"{how}")
        if problem and n8n is not None:
            report.append(f"but {problem}")

    names_in_file = set()
    result = []
    for line in lines:
        name = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#"):
            names_in_file.add(name)
            if name in want:
                line = f"{name}={want[name]}"
        result.append(line)
    for name in want:
        if name not in names_in_file:  # an .env made from an older .env.example
            result.append(f"{name}={want[name]}")
    if created:
        TARGET.touch(mode=0o600)
    TARGET.write_text("\n".join(result) + "\n", encoding="utf-8")
    if os.name == "posix":
        TARGET.chmod(0o600)

    final = si.read_env(TARGET)
    for name in ADDRESSES:
        report.append(f"  {name:<17} {final.get(name, '') or '(empty)'}")
    missing = [name for name in REQUIRED if not final.get(name)]
    return report, missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or complete deploy/.env: secrets and addresses.")
    parser.add_argument("--site", help="the DNS name or public IP address people will open")
    parser.add_argument("--allow", action="append", default=[], metavar="ADDRESS",
                        help="a public address or range that may open the portal (repeat for more)")
    parser.add_argument("--n8n-url", help="how this server reaches n8n, when n8n is on another server")
    parser.add_argument("--api-url", help="how n8n reaches the Platform API, when n8n is on another server")
    args = parser.parse_args()

    report, missing = complete(args.site, args.allow, args.n8n_url, args.api_url)
    for text in report:
        print(text)
    if missing:
        print(f"\nStill empty: {', '.join(missing)}.")
        if "SITE_ADDRESS" in missing:
            print("  SITE_ADDRESS: run this again with --site <the server's public IP or DNS name>.")
        if "N8N_WEBHOOK_BASE" in missing or "PLATFORM_API_URL" in missing:
            print("  The n8n addresses: if n8n is on another server, run this again with\n"
                  "    --n8n-url http://<n8n server>:5678 --api-url http://<this server>:8000\n"
                  "  Otherwise paste this output into the chat.")
        sys.exit(1)


if __name__ == "__main__":
    main()
