"""Port resolution and dev-server discovery.

Port 8000 is the FastAPI default, which makes it the *shared* default: a
developer running two Kaira projects, or one Kaira project beside any other
uvicorn app, meets a taken port as a matter of routine rather than as a fault.
So a busy port is treated here as a condition to resolve, not an error to
report — :func:`resolve_port` walks up from the requested port to the first one
that is actually bindable and tells the caller that it moved.

The probe binds; it does not connect.  "Is something listening there" and "can
I listen there" are different questions and only the second decides whether the
server starts: a socket bound without ``listen``, or bound on another
interface, answers the first one wrong.

Because the port the server ends up on is no longer a constant, the launcher
records it in ``.kaira/runtime.json`` and every client command
(``kaira api``, ``kaira status``, ``kaira profile`` …) reads the address back
through :func:`resolve_base_url` instead of assuming 8000.
"""

from __future__ import annotations

import errno
import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_HOST = "127.0.0.1"
"""Host ``kaira run`` binds to unless told otherwise."""

DEFAULT_PORT = 8000
"""The FastAPI default, and therefore the one most likely to be taken."""

MAX_PORT = 65535
"""Highest port number the scan may reach."""

SCAN_LIMIT = 20
"""How many consecutive ports the scan will try before giving up.

Bounded on purpose: if twenty ports in a row are taken the machine has a
problem that picking a twenty-first will not fix, and an unbounded walk to
65535 would hang the launch instead of reporting it.
"""

RUNTIME_FILE = "runtime.json"
"""Name of the record inside ``.kaira/`` naming the address the server took."""

_WINDOWS = sys.platform == "win32"

# Errors that mean "this port is not available to us".  Winsock codes are
# included by name because Python surfaces the WSA number (10048) rather than
# the POSIX one (98) on Windows, so matching on ``errno.EADDRINUSE`` alone
# would silently never fire there — the exact platform this most often runs on.
_UNAVAILABLE_ERRNOS = frozenset(
    getattr(errno, name)
    for name in ("EADDRINUSE", "WSAEADDRINUSE", "EACCES", "WSAEACCES")
    if hasattr(errno, name)
)


class PortUnavailableError(RuntimeError):
    """No bindable port was found, or the one demanded is taken.

    Attributes:
        host: Host the probe tried to bind.
        requested: Port originally asked for.
        scanned: How many candidates were tried before giving up.
    """

    def __init__(self, host: str, requested: int, scanned: int) -> None:
        self.host = host
        self.requested = requested
        self.scanned = scanned
        if scanned <= 1:
            message = f"port {requested} on {host} is already in use"
        else:
            last = min(requested + scanned - 1, MAX_PORT)
            message = f"no free port between {requested} and {last} on {host}"
        super().__init__(message)


@dataclass(frozen=True)
class PortResolution:
    """The address the server should bind, and how it was arrived at.

    Attributes:
        host: Host the ports were probed on.
        requested: Port the caller asked for.
        port: Port that is actually bindable.
        scanned: Number of candidates probed, including the winner.
    """

    host: str
    requested: int
    port: int
    scanned: int

    @property
    def shifted(self) -> bool:
        """True when the requested port was taken and the scan moved on."""
        return self.port != self.requested


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------


def _addresses(host: str, port: int) -> list[Any]:
    """Resolve *host* to the socket addresses a server would bind.

    ``getaddrinfo`` is used rather than a hardcoded ``AF_INET`` so a host given
    as ``localhost`` is probed on every family it resolves to — on a dual-stack
    machine that is both ``::1`` and ``127.0.0.1``, and a process holding only
    one of them still blocks the bind.
    """
    try:
        return list(
            socket.getaddrinfo(host or "0.0.0.0", port, type=socket.SOCK_STREAM)
        )
    except socket.gaierror:
        # An unresolvable host is not a port problem, and walking twenty ports
        # would not make it resolve.  Left for the server to report properly.
        return []


def is_port_free(host: str, port: int) -> bool:
    """Return True when a server could bind *port* on *host*.

    Inconclusive probes count as free.  A refusal we do not recognise (an
    unsupported address family, a host that is not ours to bind) says nothing
    about the port, and shifting to 8001 would not fix it — so the launch goes
    ahead and the server gets to report the real error itself.

    Args:
        host: Host the server will bind (``127.0.0.1``, ``0.0.0.0``, a name).
        port: Port to test.

    Returns:
        True if the port looks bindable, False if it is taken or barred.
    """
    for family, socktype, proto, _canonname, sockaddr in _addresses(host, port):
        try:
            with socket.socket(family, socktype, proto) as sock:
                # SO_REUSEADDR means opposite things on the two platforms: on
                # POSIX it stops a lingering TIME_WAIT socket from reporting a
                # free port as taken, on Windows it lets this bind succeed on
                # top of a live server and report a taken port as free.  So it
                # goes on everywhere except the platform it would lie on.
                if not _WINDOWS:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(sockaddr)
        except OSError as exc:
            if exc.errno in _UNAVAILABLE_ERRNOS:
                return False
            continue
    return True


def resolve_port(
    host: str = DEFAULT_HOST,
    requested: int = DEFAULT_PORT,
    *,
    strict: bool = False,
    limit: int = SCAN_LIMIT,
    probe: Optional[Callable[[str, int], bool]] = None,
) -> PortResolution:
    """Return the first bindable port at or above *requested*.

    Args:
        host: Host the server will bind.
        requested: Preferred port.
        strict: Fail on a taken port instead of moving to the next one — for
            callers where the number is part of the contract (a registered
            OAuth callback, a reverse proxy, a published container port).
        limit: Maximum number of consecutive ports to try.
        probe: Availability test, injectable so tests need no real sockets.
            Looked up on the module when omitted rather than bound as a default
            argument, so patching :func:`is_port_free` reaches this too.

    Returns:
        A :class:`PortResolution` naming the winning port and the shift.

    Raises:
        PortUnavailableError: In strict mode when *requested* is taken, or when
            *limit* consecutive ports are all unavailable.
    """
    if probe is None:
        probe = is_port_free

    if strict:
        if not probe(host, requested):
            raise PortUnavailableError(host, requested, 1)
        return PortResolution(host, requested, requested, 1)

    ceiling = min(requested + max(limit, 1), MAX_PORT + 1)
    for scanned, candidate in enumerate(range(requested, ceiling), start=1):
        if probe(host, candidate):
            return PortResolution(host, requested, candidate, scanned)
    raise PortUnavailableError(host, requested, max(ceiling - requested, 1))


# ---------------------------------------------------------------------------
# Runtime record — how the rest of the CLI finds a shifted server
# ---------------------------------------------------------------------------


def runtime_path(root: Optional[Path] = None) -> Path:
    """Return the path of the runtime record for the project at *root*."""
    return (root or Path.cwd()) / ".kaira" / RUNTIME_FILE


def record_server(host: str, port: int, root: Optional[Path] = None) -> None:
    """Note the address this run bound, for the client commands to find.

    Best-effort by design: a read-only or missing ``.kaira/`` must never stop a
    server from starting, it only costs the other commands their shortcut back
    to a non-default port.

    Args:
        host: Host the server bound.
        port: Port the server actually bound, after any shift.
        root: Project root; defaults to the current directory.
    """
    path = runtime_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"host": host, "port": port, "pid": os.getpid(), "started": time.time()}
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def clear_server(root: Optional[Path] = None) -> None:
    """Delete the runtime record once *this* run's server has stopped.

    The pid is checked first.  Two servers can be started from one project —
    the second shifts to 8001 and overwrites the record — and the second one
    exiting must not delete a record that now belongs to the first.
    """
    path = runtime_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("pid", -1)) != os.getpid():
            return
    except (OSError, ValueError, TypeError):
        # No readable record, or none of ours to interpret — fall through and
        # remove it anyway, since a record nobody can parse helps nobody.
        pass
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def read_server(root: Optional[Path] = None) -> Optional[tuple[str, int]]:
    """Return ``(host, port)`` of the server recorded for *root*, if live.

    The record is confirmed against the port before it is trusted: a crashed
    server leaves its file behind, and pointing ``kaira api`` at a port nobody
    holds is worse than pointing it at the default, because the wrong address
    then looks deliberate.
    """
    try:
        data = json.loads(runtime_path(root).read_text(encoding="utf-8"))
        host = str(data["host"])
        port = int(data["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    # Something must still be holding the port for the record to mean anything.
    if is_port_free(host, port):
        return None
    return host, port


def resolve_base_url(
    root: Optional[Path] = None, fallback_port: int = DEFAULT_PORT
) -> str:
    """Return the base URL of this project's dev server.

    Prefers the address of the running server — which may have been shifted off
    8000 — and falls back to the default when nothing is recorded or the record
    is stale.

    Args:
        root: Project root; defaults to the current directory.
        fallback_port: Port assumed when no live server is recorded.

    Returns:
        A base URL such as ``http://127.0.0.1:8001`` with no trailing slash.
    """
    recorded = read_server(root)
    if recorded is None:
        return f"http://{DEFAULT_HOST}:{fallback_port}"
    host, port = recorded
    # A server bound to every interface is not reachable *at* 0.0.0.0; the
    # loopback address is the one a client on this machine can actually use.
    if host in ("0.0.0.0", "::", ""):
        host = DEFAULT_HOST
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"
