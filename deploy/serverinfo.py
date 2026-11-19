"""What this server looks like: memory, disk, Docker, and where n8n runs.

Read-only helpers shared by deploy.py, preflight.py, new_env.py, n8n/import_to_n8n.py and send_test.py.
Nothing here changes the server. The parsing functions take text, so they can be checked without a server.
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
PROJECT = "udap"  # the `name:` of docker-compose.yml


@dataclass(frozen=True)
class Container:
    name: str
    image: str
    ports: str


@dataclass(frozen=True)
class N8n:
    """n8n on this server.

    kind            'docker' (container holds its name), 'host' (a program on the server), or 'unknown' when Docker
                    could not be asked.
    loopback_only   it answers on 127.0.0.1 but not on the server's own address, so a container cannot call it.
    """
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
    except OSError as error:
        return 126, f"{cmd[0]}: {error}"
    text = (done.stdout + done.stderr).decode("utf-8", "replace").strip()
    return done.returncode, text


_docker: list[str] | None = None


def docker() -> list[str]:
    """The command that reaches Docker here: `docker`, or `sudo -n docker` when this user may not use Docker
    directly but may use sudo without a password (the usual state of a fresh cloud server). Decided once."""
    global _docker  # noqa: PLW0603 - one answer per run
    if _docker is None:
        _docker = ["docker"]
        code, out = run(["docker", "info", "--format", "{{.ServerVersion}}"])
        if code not in (0, 127) and "permission denied" in out.lower():
            sudo_code, _ = run(["sudo", "-n", "docker", "info", "--format", "{{.ServerVersion}}"])
            if sudo_code == 0:
                _docker = ["sudo", "-n", "docker"]
    return _docker


def uses_sudo() -> bool:
    return docker()[0] == "sudo"


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


def find_n8n() -> tuple[N8n | None, str]:
    """n8n on this server, and a sentence saying how it was found.

    What decides whether the platform can use it is one test: does n8n answer on this server's own (private)
    address? A container reaches n8n there whether n8n is a container with a published port or a program.
    Docker is asked only for the container's name, which the import needs.
    """
    code, out = run([*docker(), "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"])
    container, port = None, N8N_PORT
    if code == 0:
        containers = parse_docker_ps(out)
        published = n8n_from_containers(containers)
        if published:
            container, port = published.container, published.host_port
        else:  # started with --network host: there is no port mapping to read
            on_host_network = [c for c in containers if "n8n" in c.image.lower() and "->" not in c.ports]
            if len(on_host_network) == 1:
                container = on_host_network[0].name
    address = private_ip()
    on_address = bool(address) and port_open(str(address), port)
    on_loopback = port_open("127.0.0.1", port)
    if not (on_address or on_loopback):
        if container:
            return N8n("docker", container, port, False), (
                f"n8n's container '{container}' exists, but nothing answers on port {port} yet (is it still starting?)")
        return None, f"n8n was not found on this server (nothing answers on port {port})"
    if container:
        kind, where = "docker", f"in the Docker container '{container}'"
    elif code in (0, 127):
        kind, where = "host", "directly on this server, not in a container"
    else:
        reason = out.splitlines()[-1] if out else "no output"
        kind, where = "unknown", f"on this server (Docker did not answer, so its container is not known: {reason})"
    return N8n(kind, container, port, not on_address), f"n8n runs {where} (port {port})"


def platform_running() -> bool:
    """True when this deployment's own containers are up: then ports 80, 443 and 8000 are in use by the platform."""
    code, out = run([*docker(), "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{.Names}}"])
    return code == 0 and bool(out.strip())


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
