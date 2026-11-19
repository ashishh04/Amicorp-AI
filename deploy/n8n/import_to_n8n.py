"""Load the workflow copies and their credentials into the n8n on this server, publish them, restart n8n.

    python3 n8n/import_to_n8n.py                    finds the n8n container itself
    python3 n8n/import_to_n8n.py --container n8n    when it cannot tell which container is n8n
    python3 n8n/import_to_n8n.py --yes              do not ask before starting
    python3 n8n/import_to_n8n.py --dry-run          only show the commands

What it does to n8n: adds 4 credentials and 7 workflows (the copies in n8n/out, made by
make_server_workflows.py), publishes the seven, and restarts the container, which takes about half a minute.
It never removes or re-creates the container, so n8n's own data is not touched. Running it again replaces the
same credentials and workflows (same IDs), which is how a changed address or token reaches n8n.
"""
import argparse
import json
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE.parent))
import serverinfo as si  # noqa: E402 - needs the path above

INSIDE = "/tmp/udap-import"  # noqa: S108 - a folder inside the n8n container, removed again below
CLI_TIMEOUT = 300.0
READY_SECONDS = 240
PROBE_PATH = "/webhook/bank-statement-received"


def fail(message: str, output: str = "") -> None:
    print(f"\nSTOPPED: {message}")
    if output:
        print("----- output -----")
        print(output[-3000:])
        print("------------------")
    print("Nothing was removed. Paste this into the chat if it is unclear.")
    sys.exit(1)


def expected() -> dict[str, str]:
    """Name -> ID of the workflow copies in out/."""
    files = sorted((OUT / "workflows").glob("*.json"))
    if not files or not (OUT / "credentials.json").exists():
        fail(f"{OUT} is empty. Make the copies first:  python3 n8n/make_server_workflows.py")
    return {wf["name"]: wf["id"] for wf in (json.loads(f.read_text(encoding="utf-8")) for f in files)}


def parse_list(text: str) -> dict[str, list[str]]:
    """`n8n list:workflow` prints one `id|name` per line. Returns name -> IDs."""
    found: dict[str, list[str]] = {}
    for line in text.splitlines():
        if "|" in line:
            workflow_id, name = line.split("|", 1)
            if workflow_id.strip() and " " not in workflow_id.strip():
                found.setdefault(name.strip(), []).append(workflow_id.strip())
    return found


def major_version(text: str) -> int:
    for token in text.replace("\n", " ").split():
        head = token.lstrip("v").split(".")[0]
        if head.isdigit() and "." in token:
            return int(head)
    return 2


def manual_steps() -> None:
    ids = " ".join(expected().values())
    print("n8n runs directly on this server, not in a container, so load the copies by hand.")
    print("Run these as the user that runs n8n, with the same environment as n8n itself:")
    print(f"  n8n import:credentials --input={OUT / 'credentials.json'}")
    print(f"  n8n import:workflow --separate --input={OUT / 'workflows'}")
    print(f"  for id in {ids}; do n8n publish:workflow --id=$id; done")
    print("Then restart n8n: a publish from the command line takes effect at start-up.")


def wait_until_ready(port: int) -> bool:
    """n8n answers 403 on a published webhook called without its token, and 404 while the webhook is not registered."""
    hosts = ["127.0.0.1"] + ([si.private_ip()] if si.private_ip() else [])
    deadline = time.monotonic() + READY_SECONDS
    while time.monotonic() < deadline:
        for host in hosts:
            request = urllib.request.Request(f"http://{host}:{port}{PROBE_PATH}", data=b"{}", method="POST",  # noqa: S310
                                             headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(request, timeout=5)  # noqa: S310 - this server's own n8n
            except urllib.error.HTTPError as answer:
                if answer.code == 403:
                    return True
            except OSError:
                pass
        time.sleep(4)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the UDAP workflows into the n8n container on this server.")
    parser.add_argument("--container", help="name of the n8n container (docker ps shows it)")
    parser.add_argument("--yes", action="store_true", help="do not ask before starting")
    parser.add_argument("--force", action="store_true", help="continue although n8n has workflows with the same names")
    parser.add_argument("--dry-run", action="store_true", help="show the commands without running them")
    parser.add_argument("--docker", default="docker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    docker = args.docker
    wanted = expected()

    port = si.N8N_PORT
    if args.container:
        container = args.container
        code, out = si.run([docker, "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"])
        known = si.n8n_from_containers([c for c in si.parse_docker_ps(out) if c.name == container]) if code == 0 else None
        port = known.host_port if known else port
    else:
        n8n, how = si.find_n8n(docker)
        print(how + ".")
        if n8n is None:
            fail("Give the container's name with --container, or, if n8n is on another server, copy this n8n folder "
                 "there and run this script on that server.")
        if n8n.kind != "docker":
            manual_steps()
            sys.exit(2)
        container, port = str(n8n.container), n8n.host_port

    def cli(*command: str, user: str | None = None, timeout: float = CLI_TIMEOUT) -> tuple[int, str]:
        full = [docker, "exec", *(["-u", user] if user else []), container, *command]
        if args.dry_run:
            print("  would run:", " ".join(full))
            return 0, ""
        return si.run(full, timeout=timeout)

    code, out = cli("n8n", "--version", timeout=120)
    if code != 0:
        fail(f"The n8n command does not answer in the container '{container}'.", out)
    version = out.splitlines()[-1] if out else "2.x"
    publish = (lambda wid: ("n8n", "publish:workflow", f"--id={wid}")) if major_version(version) >= 2 else \
              (lambda wid: ("n8n", "update:workflow", f"--id={wid}", "--active=true"))

    code, out = cli("n8n", "list:workflow")
    existing = parse_list(out) if code == 0 else {}
    clashes = {name: [i for i in ids if i != wanted[name]] for name, ids in existing.items() if name in wanted}
    clashes = {name: ids for name, ids in clashes.items() if ids}
    if clashes and not args.force:
        print("\nn8n already has workflows with these names under other IDs:")
        for name, ids in clashes.items():
            print(f"  {name}  ({', '.join(ids)})")
        fail("Two copies of a workflow would answer the same webhook address. In the n8n editor, unpublish or delete "
             "the ones listed above, then run this again. (--force continues anyway.)")

    print(f"\nn8n {version} in the container '{container}'. This will add 4 credentials and {len(wanted)} workflows, "
          "publish them, and restart the container (about half a minute without n8n).")
    if not (args.yes or args.dry_run):
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            sys.exit("Nothing was changed.")

    # A copy that every user in the container may read: `docker cp` gives the files to root.
    staging = Path(tempfile.mkdtemp(prefix="udap-n8n-"))
    try:
        copy = staging / Path(INSIDE).name
        shutil.copytree(OUT, copy)
        for path in [copy, *copy.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        cli("rm", "-rf", INSIDE, user="0")
        if args.dry_run:
            print(f"  would run: {docker} cp {copy} {container}:{Path(INSIDE).parent}/")
        else:
            code, out = si.run([docker, "cp", str(copy), f"{container}:{Path(INSIDE).parent}/"], timeout=120)
            if code != 0:
                fail("Copying the files into the container failed.", out)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print("Importing the credentials ...")
    code, out = cli("n8n", "import:credentials", f"--input={INSIDE}/credentials.json")
    if code != 0 or (out and "uccessfully imported" not in out):
        fail("n8n did not import the credentials.", out)
    print("Importing the workflows ...")
    code, out = cli("n8n", "import:workflow", "--separate", f"--input={INSIDE}/workflows")
    if code != 0 or (out and "uccessfully imported" not in out):
        fail("n8n did not import the workflows.", out)
    for name, workflow_id in wanted.items():
        print(f"Publishing {name} ...")
        code, out = cli(*publish(workflow_id))
        if code != 0:
            fail(f"n8n did not publish {name} ({workflow_id}).", out)
    code, out = cli("rm", "-rf", INSIDE, user="0")
    if code != 0:
        print(f"  note: could not remove {INSIDE} inside the container; it holds the tokens. It goes with the next restart"
              " only if /tmp is temporary.")

    print("Restarting n8n ...")
    if args.dry_run:
        print(f"  would run: {docker} restart {container}")
        print("Dry run finished: nothing was changed.")
        return
    code, out = si.run([docker, "restart", container], timeout=180)
    if code != 0:
        fail("The container did not restart.", out)
    print(f"Waiting for n8n to register the webhooks (up to {READY_SECONDS // 60} minutes) ...")
    if wait_until_ready(port):
        print("\nDONE: n8n is running, and the workflows answer on their webhook addresses.")
        print("Next:  python3 send_test.py")
    else:
        fail(f"n8n did not answer on port {port} in time. Look at its log:  docker logs --tail 60 {container}")


if __name__ == "__main__":
    main()
