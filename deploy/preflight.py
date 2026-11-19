"""Check that this server can take the platform. It changes nothing; run it first and read the last lines.

    python3 preflight.py

It reports memory, disk, Docker, the ports the platform needs, and where n8n runs. Each line starts with
OK, NOTE or FIX. If something is unclear, paste the whole output into the chat.
"""
import os
import platform
import sys
from pathlib import Path

import serverinfo as si

BUILD_MEMORY = 3.0 * si.GIB   # free memory plus free swap the first build needs (the portal build is the peak)
RUN_MEMORY = 1.0 * si.GIB     # what the platform uses once it runs
BUILD_DISK = 8 * si.GIB       # images, build cache and the database
SWAP_SIZE_GB = 4
PORTS = {80: "the portal (redirect to HTTPS)", 443: "the portal (HTTPS)", 8000: "the Platform API"}


def gb(value: float) -> str:
    return f"{value / si.GIB:.1f} GB"


def os_name() -> str:
    path = Path("/etc/os-release")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return platform.platform()


def main() -> int:
    fixes: list[str] = []
    notes: list[str] = []

    def line(status: str, text: str) -> None:
        print(f"  {status:<5}{text}")
        if status == "FIX":
            fixes.append(text)
        elif status == "NOTE":
            notes.append(text)

    print(f"Server: {os_name()}, {platform.machine()}, {os.cpu_count()} CPU(s)")
    if sys.platform != "linux":
        line("FIX", "This check is for the Linux server, not for the laptop.")
        return 1

    print("Memory and disk")
    mem = si.meminfo()
    available, swap_free = mem.get("MemAvailable", 0), mem.get("SwapFree", 0)
    headroom = available + swap_free
    summary = f"{gb(mem.get('MemTotal', 0))} memory, {gb(available)} free, {gb(swap_free)} free swap"
    need_swap = headroom < BUILD_MEMORY
    if need_swap:
        line("FIX", f"{summary}. The first build needs about {gb(BUILD_MEMORY)} of free memory and swap together. "
                    "Add swap first (the commands are at the end).")
    elif available < RUN_MEMORY:
        line("NOTE", f"{summary}. Enough to build with the swap, but little is left for running: expect it to be slow.")
    else:
        line("OK", summary)
    where, free = si.disk_free()
    wanted = BUILD_DISK + (SWAP_SIZE_GB * si.GIB if need_swap else 0)
    if free < wanted:
        line("FIX", f"{gb(free)} free on {where}; about {gb(wanted)} is needed. Make the disk larger (in AWS: modify the "
                    "volume, then `sudo growpart` and `sudo resize2fs`).")
    else:
        line("OK", f"{gb(free)} free on {where}")

    print("Docker")
    docker_ok = False
    code, out = si.run(["docker", "version", "--format", "{{.Server.Version}}"])
    if code == 127:
        line("FIX", "Docker is not installed:  curl -fsSL https://get.docker.com | sudo sh")
    elif code != 0:
        if "permission denied" in out.lower():
            line("FIX", "Docker is installed, but this user may not use it:  sudo usermod -aG docker $USER   "
                        "then log out and in again")
        else:
            line("FIX", f"Docker does not answer: {out.splitlines()[-1] if out else 'no output'}")
    else:
        docker_ok = True
        line("OK", f"Docker {out.splitlines()[-1]}")
    code, out = si.run(["docker", "compose", "version", "--short"])
    if code == 0:
        line("OK", f"Docker Compose {out.splitlines()[-1]}")
    elif docker_ok or code != 127:
        line("FIX", "The Compose plugin is missing:  sudo apt-get update && sudo apt-get install -y docker-compose-plugin")

    print("Ports on this server")
    for port, purpose in PORTS.items():
        if si.port_open("127.0.0.1", port):
            line("FIX", f"Port {port} is already in use here; {purpose} needs it. Paste this output into the chat.")
        else:
            line("OK", f"Port {port} is free for {purpose}")

    print("n8n")
    n8n, how = si.find_n8n()
    if n8n is None:
        line("NOTE", f"{how}. If n8n is on another server, say so in the chat.")
    else:
        line("OK", how)
        if n8n.kind == "docker":
            if n8n.loopback_only:
                line("FIX", "n8n's port is published on 127.0.0.1 only, so the Platform API (in its own container) "
                            "cannot call it back. Paste this output into the chat.")
            code, mounts = si.run(["docker", "inspect", n8n.container or "", "--format", "{{json .Mounts}}"])
            kept = si.data_mount(mounts) if code == 0 else None
            if kept:
                line("OK", f"n8n keeps its data outside the container ({kept})")
            elif code == 0:
                line("NOTE", f"n8n keeps its data INSIDE the container '{n8n.container}'. Never remove that container "
                             "(docker rm, or docker compose down): its workflows and credentials would be lost. "
                             "The steps here only restart it, which is safe.")

    print("Addresses")
    address = si.private_ip()
    line("OK" if address else "NOTE", f"private address of this server: {address or 'not found'}")
    client = si.ssh_client_ip()
    line("OK" if client else "NOTE",
         f"you are connected from: {client}" if client else
         "your own public address is not visible here (not an SSH session); you will name it yourself")

    print()
    if need_swap:
        print("Add swap (once), then run this check again:")
        print(f"  sudo fallocate -l {SWAP_SIZE_GB}G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile "
              "&& sudo swapon /swapfile")
        print("  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab")
        print()
    if fixes:
        print(f"RESULT: {len(fixes)} thing(s) to fix before you continue (the FIX lines above).")
        return 1
    print("RESULT: this server is ready." + (f" Read the {len(notes)} NOTE line(s) above." if notes else ""))
    return 0


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    sys.exit(main())
