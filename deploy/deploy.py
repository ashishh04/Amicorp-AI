"""Deploy the platform on this server and connect it to n8n: one command, safe to run again.

    python3 deploy.py                                        n8n runs on this server
    python3 deploy.py --n8n-url http://203.0.113.20:5678      n8n runs on another server

It runs the steps of deploy/README.md in order and stops at the first one that fails, saying which and why:
  1  check the server (memory, disk, Docker, where n8n runs)
  2  settings: create .env, or complete the one that exists (secrets are never replaced)
  3  build the images and start the containers
  4  wait for the Platform API, then load the sample officers and reference data
  5  make the workflow copies for n8n
  6  load them into n8n, publish them, and restart n8n (about half a minute without n8n).
     With n8n on another server it prints two commands for your laptop that do this, and waits.
  7  send a test bank statement through n8n and watch for its work card

After a stop, fix what it names and run the same command again: finished steps are quick the second time.
--site names the address people open (default: this server's public address, asked from the cloud).
--allow lets another public address open the portal. --skip-n8n stops after step 4. --yes does not ask first.
"""
import argparse
import getpass
import hashlib
import ipaddress
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
import new_env  # noqa: E402 - needs the folder above
import preflight  # noqa: E402
import serverinfo as si  # noqa: E402

TOTAL = 7
READY_SECONDS = 300
REMOTE_WAIT_SECONDS = 1200
OUT = HERE / "n8n" / "out"
STAMP = OUT / ".imported"
TRANSFER = HERE / "n8n-transfer"


def step(number: int, title: str) -> None:
    print(f"\n== Step {number} of {TOTAL}: {title} ==", flush=True)


def stopped(number: int, title: str, hint: str = "") -> None:
    print(f"\nSTOPPED at step {number} of {TOTAL} ({title}).")
    if hint:
        print(hint)
    print(f"Fix it and run the same command again. If it is unclear, copy everything from '== Step {number}' down to "
          "here into the chat.")
    sys.exit(1)


def live(command: list[str]) -> int:
    """Run a command and let it print as it goes."""
    print("  $ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=HERE, check=False).returncode  # noqa: S603


def script(*arguments: str) -> int:
    return subprocess.run([sys.executable, *arguments], cwd=HERE, check=False).returncode  # noqa: S603


def answers(url: str, host: str | None = None) -> int:
    request = urllib.request.Request(url, headers={"Host": host} if host else {})  # noqa: S310 - this deployment
    try:
        with urllib.request.urlopen(request, timeout=6) as answer:  # noqa: S310
            return int(answer.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except OSError:
        return 0


def wait_for_api(port: str) -> bool:
    hosts = ["127.0.0.1"] + ([si.private_ip()] if si.private_ip() else [])
    deadline = time.monotonic() + READY_SECONDS
    while time.monotonic() < deadline:
        if any(answers(f"http://{host}:{port}/ready") == 200 for host in hosts):
            return True
        time.sleep(4)
    return False


def copies_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in OUT.rglob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def n8n_probe(base: str, token: str) -> int:
    """Call the statement webhook with the current token and an empty body. The workflow answers 400 to that
    (nothing is registered), so 400 means n8n has these workflows published with the current credentials.
    403: other credentials. 404: not published. 0: n8n cannot be reached."""
    request = urllib.request.Request(f"{base}/webhook/bank-statement-received", data=b"{}", method="POST",  # noqa: S310
                                     headers={"Content-Type": "application/json", "X-Webhook-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:  # noqa: S310 - this deployment's own n8n
            return int(answer.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except OSError:
        return 0


def prepare_transfer() -> None:
    """A folder that holds everything the n8n server needs: the import script, its helper and the copies."""
    shutil.rmtree(TRANSFER, ignore_errors=True)
    TRANSFER.mkdir()
    shutil.copy(HERE / "n8n" / "import_to_n8n.py", TRANSFER / "import_to_n8n.py")
    shutil.copy(HERE / "serverinfo.py", TRANSFER / "serverinfo.py")
    shutil.copytree(OUT, TRANSFER / "out", ignore=shutil.ignore_patterns(".imported"))
    if os.name == "posix":
        TRANSFER.chmod(0o700)


def load_on_other_server(base: str, token: str, own: str | None) -> bool:
    """n8n is on another server: say exactly what to run on the laptop, wait, then check that n8n has the copies."""
    prepare_transfer()
    n8n_host = new_env.host_of(base)
    here = TRANSFER.relative_to(Path.home()).as_posix() if TRANSFER.is_relative_to(Path.home()) else TRANSFER.as_posix()
    target = f"udap-n8n-{secrets.token_hex(2)}"
    print("  n8n runs on another server, so its workflows are loaded there. On your LAPTOP (PowerShell), run:")
    print()
    print(f"    scp -3 -r -i <your-key.pem> {getpass.getuser()}@{own or '<this server>'}:{here} ubuntu@{n8n_host}:{target}")
    print(f'    ssh -i <your-key.pem> ubuntu@{n8n_host} "python3 {target}/import_to_n8n.py --yes && rm -rf {target}"')
    print()
    print("  The first copies the workflow copies from this server to the n8n server. The second loads them into n8n,")
    print("  publishes them and restarts n8n once; it ends with DONE. Use your own key file, and your own user name")
    if si.is_ip(n8n_host) and not ipaddress.ip_address(n8n_host).is_global:
        print(f"  instead of ubuntu if it differs. {n8n_host} is a private address: from the laptop, use the n8n")
        print("  server's public address in both commands.")
    else:
        print("  instead of ubuntu if it differs.")
    try:
        input("\n  Press Enter here when the second command has printed DONE ... ")
    except EOFError:  # no keyboard: watch n8n instead
        deadline = time.monotonic() + REMOTE_WAIT_SECONDS
        while time.monotonic() < deadline and n8n_probe(base, token) != 400:
            time.sleep(6)
    code = n8n_probe(base, token)
    if code == 400:
        print("  n8n has the workflows, published, with the current credentials")
        return True
    reason = {403: "n8n answers, but with other credentials than this server's: the second command did not finish",
              404: "n8n does not know the webhooks yet: the second command did not finish (it must end with DONE)",
              0: f"this server cannot reach n8n at {base}"}.get(code, f"n8n answered HTTP {code}")
    print(f"  {reason}.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy the platform on this server and connect it to n8n.")
    parser.add_argument("--site", help="the address people open: a DNS name or this server's public IP (default: asked "
                                       "from the cloud)")
    parser.add_argument("--allow", action="append", default=[], metavar="ADDRESS",
                        help="a public address or range that may open the portal (repeat for more)")
    parser.add_argument("--n8n-url", help="n8n's address, when n8n runs on another server: http://<address>:5678")
    parser.add_argument("--api-url", help="how that n8n reaches the Platform API (default: worked out from --n8n-url)")
    parser.add_argument("--skip-n8n", action="store_true", help="stop after the platform itself runs (step 4)")
    parser.add_argument("--yes", action="store_true", help="do not ask before starting")
    args = parser.parse_args()

    step(1, "check the server")
    if preflight.main() != 0:
        stopped(1, "check the server", "The FIX lines above say what to do; each one gives its command.")
    docker = si.docker()

    step(2, "settings")
    own = si.public_ip()
    site = args.site.strip().removeprefix("https://").removeprefix("http://").rstrip("/") if args.site else None
    n8n_url = args.n8n_url
    local_n8n, _ = si.find_n8n()
    existing = si.read_env(HERE / ".env").get("SITE_ADDRESS", "")
    if site and own and si.is_ip(site) and site != own:
        if not n8n_url and local_n8n is None and answers(f"http://{site}:{si.N8N_PORT}/healthz") == 200:
            print(f"  NOTE  {site} is your n8n server, not this one: this server's public address is {own}.")
            print(f"        Using {own} for the portal and http://{site}:{si.N8N_PORT} for n8n.")
            n8n_url, site = f"http://{site}:{si.N8N_PORT}", own
        else:
            print(f"  NOTE  --site {site} is not this server's public address ({own}); using what you gave.")
    elif not site and own and si.is_ip(existing) and existing != own:
        print(f"  NOTE  The settings had {existing} as this server's address, but its public address is {own}: corrected.")
        site = own
    report, missing = new_env.complete(site, args.allow, n8n_url, args.api_url)
    for text in report:
        print("  " + text)
    if missing:
        hints = []
        if "SITE_ADDRESS" in missing:
            hints.append("This server's public address is not known here. Add it:  --site <public IP or DNS name>")
        if "N8N_WEBHOOK_BASE" in missing or "PLATFORM_API_URL" in missing:
            hints.append("n8n was not found on this server. It runs on another server, so add its address:\n"
                         "    python3 deploy.py --n8n-url http://<n8n's address>:5678")
        stopped(2, "settings", "\n".join(hints))
    env = si.read_env(HERE / ".env")
    base = env["N8N_WEBHOOK_BASE"].rstrip("/")
    n8n_host = new_env.host_of(base)
    remote = n8n_host not in {si.private_ip(), "127.0.0.1", "localhost"}
    if remote and not args.skip_n8n:
        if answers(f"{base}/healthz") != 200:
            stopped(2, "settings", f"This server cannot reach n8n at {base}. Is the address right? In the n8n server's cloud "
                                   f"firewall (AWS: its security group), port {base.rsplit(':', 1)[-1]} must be open to "
                                   f"this server's address ({own or si.private_ip()}).")
        print(f"  n8n answers at {base} (another server)")
        print(f"  NOTE  n8n will call the Platform API at {env['PLATFORM_API_URL']}. In THIS server's cloud firewall (AWS: its")
        print(f"        security group), open port {env.get('API_PORT') or '8000'} to the n8n server ({n8n_host}) and to nobody else.")

    if not args.yes:
        what = "" if args.skip_n8n else (
            ", then give you two commands that load 7 workflows into n8n and restart it once" if remote else
            ", then add 7 workflows to n8n and restart n8n once (about half a minute without n8n)")
        print(f"\nNext: build and start the platform on this server (5 to 10 minutes the first time){what}.")
        try:
            agreed = input("Continue? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            agreed = False
        if not agreed:
            sys.exit("Nothing was started. Run it again and answer y, or add --yes.")

    step(3, "build the images and start the containers")
    if live([*docker, "compose", "up", "-d", "--build"]) != 0:
        stopped(3, "build and start", "The error is in the lines above.")

    step(4, "wait for the Platform API, then load the sample data")
    port = env.get("API_PORT") or "8000"
    if not wait_for_api(port):
        live([*docker, "compose", "ps", "-a"])
        live([*docker, "compose", "logs", "--tail", "40", "migrate", "api"])
        stopped(4, "wait for the Platform API", f"The API did not answer on port {port} within {READY_SECONDS // 60} minutes.")
    print("  the Platform API is ready")
    if live([*docker, "compose", "exec", "-T", "api", "python", "-m", "scripts.seed"]) != 0:
        stopped(4, "load the sample data")
    gateway = answers(f"http://127.0.0.1:{env.get('GATEWAY_HTTP_PORT') or '80'}/healthz", host="localhost")
    print("  the gateway answers" if gateway == 200 else
          f"  NOTE  the gateway did not answer on this server (HTTP {gateway}); see: docker compose logs gateway")
    if args.skip_n8n:
        print("\nThe platform runs. n8n was left alone (--skip-n8n).")
        return

    step(5, "make the workflow copies for n8n")
    if script("n8n/make_server_workflows.py") != 0:
        stopped(5, "make the workflow copies")

    step(6, "load them into n8n")
    fingerprint = copies_fingerprint()
    token = env.get("N8N_INTAKE_WEBHOOK_TOKEN", "")
    if STAMP.exists() and STAMP.read_text(encoding="utf-8").strip() == fingerprint and n8n_probe(base, token) == 400:
        print("  n8n already has exactly these copies, published: nothing to do")
    elif remote:
        if not load_on_other_server(base, token, own):
            stopped(6, "load them into n8n", "Run the two commands again (they are above), or paste their output into the chat.")
        STAMP.write_text(fingerprint + "\n", encoding="utf-8")
    else:
        code = script("n8n/import_to_n8n.py", "--yes")
        if code == 2:
            stopped(6, "load them into n8n", "n8n runs without Docker here, so run the commands printed above as the user "
                                              "that runs n8n, restart n8n, and then run:  python3 deploy.py")
        if code != 0:
            stopped(6, "load them into n8n")
        STAMP.write_text(fingerprint + "\n", encoding="utf-8")

    step(7, "send a test bank statement and watch for its card")
    if script("send_test.py") != 0:
        stopped(7, "end-to-end test")

    print("\nDEPLOYED.")
    print(f"  Portal:   https://{env.get('SITE_ADDRESS', '')}")
    print("            The browser warns about the certificate once (when the address is an IP): Advanced, then Proceed.")
    print("            Sign in as any sample officer, for example Chan Tai Man.")
    print("  If the page does not open: in this server's cloud firewall (AWS: its security group), open port 443 to your "
          "own address.")
    if si.uses_sudo():
        print("  Docker runs through sudo on this server: type `sudo docker compose ps`, `sudo docker compose logs -f api`.")


if __name__ == "__main__":
    main()
