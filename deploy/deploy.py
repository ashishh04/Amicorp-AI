"""Deploy the platform on this server and connect it to n8n: one command, safe to run again.

    python3 deploy.py --site 203.0.113.10        the server's public IP address, or its DNS name

It runs the steps of deploy/README.md in order and stops at the first one that fails, saying which and why:
  1  check the server (memory, disk, Docker, where n8n runs)
  2  settings: create .env, or complete the one that exists (secrets and addresses are never replaced)
  3  build the images and start the containers
  4  wait for the Platform API, then load the sample officers and reference data
  5  make the workflow copies for n8n
  6  load them into n8n, publish them, and restart n8n (about half a minute without n8n)
  7  send a test bank statement through n8n and watch for its work card

After a stop, fix what it names and run the same command again: finished steps are quick the second time.
--skip-n8n stops after step 4. --yes does not ask before it starts.
"""
import argparse
import hashlib
import os
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
OUT = HERE / "n8n" / "out"
STAMP = OUT / ".imported"


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
    request = urllib.request.Request(url, headers={"Host": host} if host else {})  # noqa: S310 - this server itself
    try:
        with urllib.request.urlopen(request, timeout=5) as answer:  # noqa: S310
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


def webhooks_answer(base: str) -> bool:
    """A published n8n webhook answers 403 when it is called without its token (404 when it is not registered)."""
    request = urllib.request.Request(f"{base}/webhook/bank-statement-received", data=b"{}", method="POST",  # noqa: S310
                                     headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=8)  # noqa: S310 - this deployment's own n8n
    except urllib.error.HTTPError as error:
        return error.code == 403
    except OSError:
        return False
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy the platform on this server and connect it to n8n.")
    parser.add_argument("--site", help="the server's public IP address or DNS name (needed the first time)")
    parser.add_argument("--allow", action="append", default=[], metavar="ADDRESS",
                        help="a public address or range that may open the portal (repeat for more)")
    parser.add_argument("--n8n-url", help="how this server reaches n8n, when n8n is on another server")
    parser.add_argument("--api-url", help="how n8n reaches the Platform API, when n8n is on another server")
    parser.add_argument("--skip-n8n", action="store_true", help="stop after the platform itself runs (step 4)")
    parser.add_argument("--yes", action="store_true", help="do not ask before starting")
    args = parser.parse_args()

    step(1, "check the server")
    if preflight.main() != 0:
        stopped(1, "check the server", "The FIX lines above say what to do; each one gives its command.")
    docker = si.docker()

    step(2, "settings")
    report, missing = new_env.complete(args.site, args.allow, args.n8n_url, args.api_url)
    for text in report:
        print("  " + text)
    if missing:
        hints = []
        if "SITE_ADDRESS" in missing:
            hints.append("Add the server's public address:  python3 deploy.py --site <public IP or DNS name>")
        if "N8N_WEBHOOK_BASE" in missing or "PLATFORM_API_URL" in missing:
            hints.append("n8n was not found on this server. If n8n runs on another server, add\n"
                         "    --n8n-url http://<n8n server>:5678 --api-url http://<this server>:8000\n"
                         "and open port 8000 of this server to the n8n server only.")
        stopped(2, "settings", "\n".join(hints))
    env = si.read_env(HERE / ".env")

    if not args.yes:
        print("\nNext: build and start the platform on this server (5 to 10 minutes the first time)"
              + ("" if args.skip_n8n else ", then add 7 workflows to n8n and restart n8n once (about half a minute "
                                          "without n8n)") + ".")
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
          f"  NOTE: the gateway did not answer on this server (HTTP {gateway}); see: docker compose logs gateway")
    if args.skip_n8n:
        print("\nThe platform runs. n8n was left alone (--skip-n8n).")
        return

    step(5, "make the workflow copies for n8n")
    if script("n8n/make_server_workflows.py") != 0:
        stopped(5, "make the workflow copies")

    step(6, "load them into n8n")
    fingerprint = copies_fingerprint()
    base = env.get("N8N_WEBHOOK_BASE", "").rstrip("/")
    if STAMP.exists() and STAMP.read_text(encoding="utf-8").strip() == fingerprint and webhooks_answer(base):
        print("  n8n already has exactly these copies, and its webhooks answer: nothing to do")
    else:
        code = script("n8n/import_to_n8n.py", "--yes")
        if code == 2:
            stopped(6, "load them into n8n", "n8n runs without Docker here, so run the commands printed above as the user "
                                              "that runs n8n, restart n8n, and then run:  python3 send_test.py")
        if code != 0:
            stopped(6, "load them into n8n")
        STAMP.write_text(fingerprint + "\n", encoding="utf-8")

    step(7, "send a test bank statement and watch for its card")
    if script("send_test.py") != 0:
        stopped(7, "end-to-end test")

    site = env.get("SITE_ADDRESS", "")
    print("\nDEPLOYED.")
    print(f"  Portal:   https://{site}")
    print("            The browser warns about the certificate once (when the address is an IP): Advanced, then Proceed.")
    print("            Sign in as any sample officer, for example Chan Tai Man.")
    print("  If the page does not open: in the cloud firewall (AWS: the security group) open port 443 to your address.")
    if si.uses_sudo():
        print("  Docker runs through sudo on this server: type `sudo docker compose ps`, `sudo docker compose logs -f api`.")


if __name__ == "__main__":
    main()
