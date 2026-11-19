"""Create or complete deploy/.env: a value for every secret, and the addresses.

    python3 new_env.py                                        n8n runs on this server
    python3 new_env.py --n8n-url http://203.0.113.20:5678      n8n runs on another server
    python3 new_env.py --site udap.example.com                 people open a DNS name instead of the IP address

The first run copies .env.example and fills it in. A later run completes the same file and is safe to repeat:
it never replaces a secret or an n8n address that is already set, because the database and n8n use them.
SITE_ADDRESS follows --site, and the n8n addresses follow --n8n-url, when you give them.

Without --site it asks the cloud for this server's public address. With n8n on this server it uses the
server's own (private) address for both directions. With n8n on another server, n8n reaches the Platform API on
the private address when n8n's own address is private, otherwise on this server's public address.
--allow adds public addresses that may open the portal; if none is set, the address you are connected from is used.
deploy.py runs this for you.
"""
import argparse
import ipaddress
import os
import secrets
import sys
import urllib.parse
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


def host_of(url: str) -> str:
    return urllib.parse.urlsplit(url if "//" in url else f"//{url}").hostname or ""


def api_url_for(n8n_url: str, site: str | None) -> str | None:
    """How an n8n on another server reaches the Platform API: over the private network when n8n's own address is
    private, otherwise at this server's public address."""
    host = host_of(n8n_url)
    if si.is_ip(host) and ipaddress.ip_address(host).is_private:
        own = si.private_ip()
        return f"http://{own}:{API_PORT}" if own else None
    return f"http://{site}:{API_PORT}" if site else None


def complete(site: str | None = None, allow: list[str] | None = None, n8n_url: str | None = None,
             api_url: str | None = None) -> tuple[list[str], list[str]]:
    """Create .env, or complete the one that exists. Returns (what it did, which required values are still empty)."""
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
    elif not current.get("SITE_ADDRESS"):
        public = si.public_ip()
        if public:
            want["SITE_ADDRESS"] = public
            report.append(f"this server's public address is {public} (asked from the cloud)")
    site_now = want.get("SITE_ADDRESS") or current.get("SITE_ADDRESS")

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

    if n8n_url:
        n8n_url = (n8n_url if "//" in n8n_url else f"http://{n8n_url}").rstrip("/")
        api = (api_url or api_url_for(n8n_url, site_now) or "").rstrip("/")
        want.update({"N8N_WEBHOOK_BASE": n8n_url, "API_BIND": "0.0.0.0"})  # noqa: S104 - n8n calls from another server
        if api:
            want["PLATFORM_API_URL"] = api
        report.append("n8n is on another server")
    elif not (current.get("PLATFORM_API_URL") and current.get("N8N_WEBHOOK_BASE")):
        n8n, how = si.find_n8n()
        found, problem = n8n_addresses(n8n, si.private_ip())
        want.update(found)
        report.append(how)
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
    parser.add_argument("--site", help="the DNS name or public IP address people will open (default: asked from the cloud)")
    parser.add_argument("--allow", action="append", default=[], metavar="ADDRESS",
                        help="a public address or range that may open the portal (repeat for more)")
    parser.add_argument("--n8n-url", help="n8n's address, when n8n is on another server: http://<address>:5678")
    parser.add_argument("--api-url", help="how that n8n reaches the Platform API (default: worked out from --n8n-url)")
    args = parser.parse_args()

    report, missing = complete(args.site, args.allow, args.n8n_url, args.api_url)
    for text in report:
        print(text)
    if missing:
        print(f"\nStill empty: {', '.join(missing)}.")
        if "SITE_ADDRESS" in missing:
            print("  SITE_ADDRESS: run this again with --site <the server's public IP or DNS name>.")
        if "N8N_WEBHOOK_BASE" in missing or "PLATFORM_API_URL" in missing:
            print("  n8n is not on this server: run this again with --n8n-url http://<n8n's address>:5678")
        sys.exit(1)


if __name__ == "__main__":
    main()
