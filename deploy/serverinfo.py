"""What this server looks like: memory, disk, Docker, and where n8n runs.

Read-only helpers shared by preflight.py, new_env.py, n8n/import_to_n8n.py and send_test.py. Nothing here
changes the server. The parsing functions take text, so they can be checked without a server.
"""
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

N8N_PORT = 5678
GIB = 1024 ** 3


@dataclass(frozen=True)
class Container:
    name: str
    image: str
    ports: str


@dataclass(frozen=True)
class N8n:
    """Where n8n runs on this server. kind is 'docker' (container holds its name) or 'host'."""
    kind: str
    container: str | None
    host_port: int
    loopback_only: bool


def run(cmd: list[str], timeout: float = 20.0, stdin: bytes | None = None) -> tuple[int, str]:
    """Run a command; never raises. Returns (exit code, output). 127 means the program is not installed."""
    try:
        done = subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout, check=False)  # noqa: S603
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not installed"
    except subprocess.TimeoutExpired:
        return 124, f"{' '.join(cmd[:3])}: no answer within {timeout:.0f} s"
    text = (done.stdout + done.stderr).decode("utf-8", "replace").strip()
    return done.returncode, text


def parse_meminfo(text: str) -> dict[str, int]:
    """/proc/meminfo as bytes per field (MemTotal, MemAvailable, SwapTotal, SwapFree, ...)."""
    values: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"^(\w+):\s+(\d+)\s*kB", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    return values


def meminfo() -> dict[str, int]:
    path = Path("/proc/meminfo")
    return parse_meminfo(path.read_text(encoding="utf-8")) if path.exists() else {}


def disk_free(path: str = "/var/lib/docker") -> tuple[str, int]:
    """Free bytes where Docker keeps its data (or on / when Docker is not installed yet)."""
    target = path if os.path.isdir(path) else "/"
    try:
        return target, shutil.disk_usage(target).free
    except OSError:  # /var/lib/docker is readable by root only on some systems
        return "/", shutil.disk_usage("/").free


def private_ip() -> str | None:
    """The address of the network interface this server uses to reach other machines. Sends nothing."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # a documentation address: connect() on UDP only picks the route
        return str(probe.getsockname()[0])
    except OSError:
        return None
    finally:
        probe.close()


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ssh_client_ip(environ: dict[str, str] | None = None) -> str | None:
    """The public address you are connected from (SSH_CONNECTION), or None."""
    value = (environ if environ is not None else dict(os.environ)).get("SSH_CONNECTION", "")
    first = value.split()[0] if value.split() else ""
    try:
        address = ipaddress.ip_address(first)
    except ValueError:
        return None
    return str(address) if address.version == 4 and address.is_global else None


def parse_docker_ps(text: str) -> list[Container]:
    """Lines of `docker ps --format '{{.Names}}\\t{{.Image}}\\t{{.Ports}}'`."""
    containers = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            containers.append(Container(parts[0].strip(), parts[1].strip(), parts[2].strip() if len(parts) > 2 else ""))
    return containers


def n8n_from_containers(containers: list[Container], port: int = N8N_PORT) -> N8n | None:
    """The container that publishes n8n's port. A container whose image is n8n but publishes nothing does not count:
    nothing outside it could call its webhooks."""
    pattern = re.compile(r"(?:(\[[0-9a-fA-F:]*\]|[0-9.]+):)?(\d+)->" + str(port) + r"/tcp")
    for container in containers:
        published = pattern.findall(container.ports)
        if not published:
            continue
        hosts = {host or "0.0.0.0" for host, _ in published}  # noqa: S104 - parsing Docker's notation
        loopback_only = all(host.startswith("127.") or host == "[::1]" for host in hosts)
        return N8n("docker", container.name, int(published[0][1]), loopback_only)
    return None


def find_n8n(docker: str = "docker") -> tuple[N8n | None, str]:
    """n8n on this server, and a sentence saying how it was found."""
    code, out = run([docker, "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"])
    if code not in (0, 127):
        # Docker is installed but did not answer (usually: this user may not use it). Do not guess from the open
        # port: a container's published port looks the same as a program on the server.
        reason = out.splitlines()[-1] if out else "no output"
        return None, f"Docker did not answer, so n8n could not be looked for ({reason})"
    listening = port_open("127.0.0.1", N8N_PORT)
    if code == 0:
        containers = parse_docker_ps(out)
        found = n8n_from_containers(containers)
        if found:
            return found, f"n8n runs in the Docker container '{found.container}' (port {found.host_port})"
        on_host_network = [c for c in containers if "n8n" in c.image.lower() and "->" not in c.ports]
        if listening and len(on_host_network) == 1:  # started with --network host: no port mapping to read
            name = on_host_network[0].name
            return N8n("docker", name, N8N_PORT, False), f"n8n runs in the Docker container '{name}' (host network)"
    if listening:
        return N8n("host", None, N8N_PORT, False), f"n8n runs directly on this server (port {N8N_PORT}, no container)"
    return None, f"n8n was not found on this server (no container publishes port {N8N_PORT}, and nothing listens on it)"


def data_mount(inspect_json: str, inside: str = "/home/node/.n8n") -> str | None:
    """Where the container keeps n8n's data on the server: a volume or folder name, or None when the data lives
    inside the container itself (then removing the container deletes every workflow and credential)."""
    try:
        mounts = json.loads(inspect_json)
    except ValueError:
        return None
    for mount in mounts or []:
        destination = str(mount.get("Destination", "")).rstrip("/")
        if destination and (inside == destination or inside.startswith(destination + "/")):
            return str(mount.get("Name") or mount.get("Source") or "a volume")
    return None


def read_env(path: Path) -> dict[str, str]:
    """A .env file as a dictionary (quotes around a value are removed)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[name.strip()] = value
    return values
