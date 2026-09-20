"""Kaira loadtest command group — concurrent load testing for local routes.

SECURITY: Remote hosts are blocked unless --allow-remote is passed AND the user
types the hostname to confirm. This prevents accidental load-testing of production
or third-party services. Uses httpx.AsyncClient with a bounded asyncio.Semaphore.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Annotated
from urllib.parse import urlparse

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

app = typer.Typer(help="Load testing for local FastAPI routes.")


def _base_url() -> str:
    """Return the base URL of this project's dev server.

    Resolved per call rather than fixed at import: ``kaira run`` moves off a
    taken port and records where it landed, so a constant baked in at import
    time would point at :8000 while the server answers on :8001.
    """
    from kaira.core.ports import resolve_base_url

    return resolve_base_url()


_LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _is_localhost(host: str) -> bool:
    """Check whether a host resolves to localhost.

    Args:
        host: Hostname or IP address.

    Returns:
        True if the host is a localhost variant.
    """
    return host.lower() in _LOCALHOST_HOSTS


async def _run_loadtest(
    method: str,
    url: str,
    total: int,
    concurrency: int,
) -> list[float]:
    """Execute a concurrent load test using httpx.AsyncClient with a semaphore.

    Args:
        method: HTTP method.
        url: Full URL to test.
        total: Total number of requests.
        concurrency: Maximum concurrent requests.

    Returns:
        List of response latencies in milliseconds.
    """
    import httpx

    sem = asyncio.Semaphore(concurrency)
    times: list[float] = []

    async def _one_request(client: httpx.AsyncClient) -> None:
        async with sem:
            start = time.perf_counter()
            try:
                await client.request(method.upper(), url)
            except Exception:
                pass
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = [_one_request(client) for _ in range(total)]
        await asyncio.gather(*tasks)

    return times


@app.command("run")
def loadtest_run(
    method: Annotated[str, typer.Argument(help="HTTP method: GET, POST, etc.")],
    route: Annotated[str, typer.Argument(help="Route path or full URL")],
    requests_n: Annotated[
        int, typer.Option("--requests", "-n", help="Total request count")
    ] = 100,
    concurrency: Annotated[
        int, typer.Option("--concurrency", "-c", help="Concurrent request count")
    ] = 10,
    allow_remote: Annotated[
        bool,
        typer.Option("--allow-remote", help="Allow targeting a non-localhost host"),
    ] = False,
) -> None:
    """Run a concurrent load test against a route.

    Blocked against remote hosts unless --allow-remote is passed AND the hostname
    is typed to confirm — preventing accidental production load tests.

    Args:
        method: HTTP method.
        route: Route path (e.g. /users) or full URL.
        requests_n: Total number of requests to send.
        concurrency: Maximum simultaneous connections.
        allow_remote: Allow non-localhost targets (requires typed confirmation).
    """
    # Build full URL
    if route.startswith("http"):
        full_url = route
    else:
        full_url = f"{_base_url()}{route}"

    parsed = urlparse(full_url)
    host = parsed.hostname or "localhost"

    # Block remote hosts unless explicitly allowed + confirmed
    if not _is_localhost(host):
        if not allow_remote:
            console.print(
                Panel(
                    f"[red]❌ Blocked: refusing to load-test a remote host without explicit confirmation.\n\n"
                    f"If you really intend to load-test [bold]{host}[/bold], run:\n"
                    f"  [cyan]kaira loadtest run {method} {route} --allow-remote[/cyan]\n\n"
                    f"You will be asked to type the hostname to confirm.[/red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

        # Require typed hostname confirmation
        console.print(
            f"[yellow]⚠️  You are about to load-test a remote host: [bold]{host}[/bold][/yellow]\n"
            f"Type the hostname to confirm, or press Enter to abort:"
        )
        answer = typer.prompt("", default="")
        if answer.strip().lower() != host.lower():
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    console.print(
        Panel(
            f"[cyan]Load testing {method.upper()} {full_url}\n"
            f"Requests: {requests_n}  |  Concurrency: {concurrency}[/cyan]",
            border_style="cyan",
        )
    )

    try:
        times = asyncio.run(_run_loadtest(method, full_url, requests_n, concurrency))
    except ImportError:
        console.print("[red]❌ httpx not installed. Run: pip install httpx[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]❌ Load test error: {type(exc).__name__}[/red]")
        raise typer.Exit(1)

    if not times:
        console.print("[red]❌ No responses received.[/red]")
        raise typer.Exit(1)

    sorted_times = sorted(times)
    p50 = statistics.median(times)
    p95 = sorted_times[int(len(sorted_times) * 0.95)]
    p99 = sorted_times[min(int(len(sorted_times) * 0.99), len(sorted_times) - 1)]

    table = Table(title=f"Load Test: {method.upper()} {full_url}", border_style="cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Total Requests", str(requests_n))
    table.add_row("Concurrency", str(concurrency))
    table.add_row("Avg", f"{statistics.mean(times):.2f}ms")
    table.add_row("p50 (median)", f"{p50:.2f}ms")
    table.add_row("p95", f"{p95:.2f}ms")
    table.add_row("p99", f"{p99:.2f}ms")
    table.add_row("Min", f"{min(times):.2f}ms")
    table.add_row("Max", f"{max(times):.2f}ms")
    table.add_row("RPS (approx)", f"{requests_n / (sum(times) / 1000):.1f}")
    console.print(table)
