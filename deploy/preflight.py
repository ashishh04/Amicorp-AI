"""Check that this server can take the platform. It changes nothing.

    python3 preflight.py

It reports memory, disk, Docker, the ports the platform needs, and where n8n runs. Each line starts with
OK, NOTE or FIX, and the last line is the RESULT. deploy.py runs this first.
"""
import os
import platform
import sys
from pathlib import Path

import serverinfo as si

BUILD_MEMORY = 4.5 * si.GIB   # free memory plus free swap for the first build: the portal build alone may take 3 GB
RUN_MEMORY = 1.0 * si.GIB     # what the platform uses once it runs
BUILD_DISK = 8 * si.GIB       # images, build cache and the database
SWAP_SIZE_GB = 4
PORTS = {80: "the portal (redirect to HTTPS)", 443: "the portal (HTTPS)", 8000: "the Platform API"}
# Docker's own packages are named ...-plugin; Ubuntu's are docker-compose-v2 and docker-buildx.
INSTALL_PLUGINS = ("sudo apt-get update && (sudo apt-get install -y docker-compose-plugin docker-buildx-plugin "
                   "|| sudo apt-get install -y docker-compose-v2 docker-buildx)")


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

    print("Docker")
    docker = si.docker()
    docker_ok = False
    code, out = si.run([*docker, "version", "--format", "{{.Server.Version}}"])
    if code == 127:
        line("FIX", "Docker is not installed:  curl -fsSL https://get.docker.com | sudo sh")
    elif code != 0:
        if "permission denied" in out.lower():
            line("FIX", "Docker is installed, but this user may not use it and sudo asks for a password:  "
                        "sudo usermod -aG docker $USER   then log out and in again")
        else:
            line("FIX", f"Docker does not answer: {out.splitlines()[-1] if out else 'no output'}")
    else:
        docker_ok = True
        line("OK", f"Docker {out.splitlines()[-1]}" + (" (through sudo)" if si.uses_sudo() else ""))
        if si.uses_sudo():
            line("NOTE", "This user reaches Docker only through sudo, so type `sudo docker ...` yourself. "
                         "To drop the sudo:  sudo usermod -aG docker $USER   then log out and in again")
    if docker_ok:
        compose_code, compose = si.run([*docker, "compose", "version", "--short"])
        buildx_code, buildx = si.run([*docker, "buildx", "version"])
        if compose_code == 0 and buildx_code == 0:
            line("OK", f"Docker Compose {compose.splitlines()[-1]}, with buildx")
        else:
            missing = " and ".join(name for name, c in (("Compose", compose_code), ("buildx", buildx_code)) if c != 0)
            line("FIX", f"Docker's {missing} plugin is missing:  {INSTALL_PLUGINS}")
    running = docker_ok and si.platform_running()
    if running:
        line("OK", "The platform's containers are already running here (this is a repeat run)")

    print("Memory and disk")
    mem = si.meminfo()
    available, swap_free = mem.get("MemAvailable", 0), mem.get("SwapFree", 0)
    summary = f"{gb(mem.get('MemTotal', 0))} memory, {gb(available)} free, {gb(swap_free)} free swap"
    need_swap = available + swap_free < BUILD_MEMORY and not running
    if need_swap:
        line("FIX", f"{summary}. The first build needs about {gb(BUILD_MEMORY)} of free memory and swap together. "
                    "Add swap first (the commands are at the end).")
    elif available < RUN_MEMORY and not running:
        line("NOTE", f"{summary}. Enough to build with the swap, but little is left for running: expect it to be slow.")
    else:
        line("OK", summary)
    where, free = si.disk_free()
    wanted = (2 if running else BUILD_DISK / si.GIB) * si.GIB + (SWAP_SIZE_GB * si.GIB if need_swap else 0)
    if free < wanted:
        line("FIX", f"{gb(free)} free on {where}; about {gb(wanted)} is needed. Make the disk larger (in AWS: modify the "
                    "volume, then `sudo growpart` and `sudo resize2fs`).")
    else:
        line("OK", f"{gb(free)} free on {where}")

    print("Ports on this server")
    for port, purpose in PORTS.items():
        if not si.port_open("127.0.0.1", port):
            line("OK", f"Port {port} is free for {purpose}")
        elif running:
            line("OK", f"Port {port} is in use by the platform itself")
        else:
            line("FIX", f"Port {port} is already in use by another program; {purpose} needs it. "
                        "Paste this output into the chat.")

    print("n8n")
    n8n, how = si.find_n8n()
    if n8n is None:
        line("NOTE", f"{how}. If n8n runs on another server, give its address:  --n8n-url http://<n8n's address>:5678")
    else:
        line("OK", how)
        if n8n.loopback_only:
            line("FIX", "n8n answers on 127.0.0.1 only, so the Platform API (in its own container) cannot call it "
                        "back. Paste this output into the chat.")
        if n8n.kind == "docker":
            code, mounts = si.run([*docker, "inspect", n8n.container or "", "--format", "{{json .Mounts}}"])
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
    public = si.public_ip()
    line("OK" if public else "NOTE", f"public address of this server: {public}" if public else
         "public address of this server: not known here (give it with --site)")
    client = si.ssh_client_ip()
    line("OK" if client else "NOTE",
         f"you are connected from: {client}" if client else
         "your own public address is not visible here (not an SSH session); the portal will name it when it refuses you")

    print()
    if need_swap:
        print("Add swap (once), then run the command again:")
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
