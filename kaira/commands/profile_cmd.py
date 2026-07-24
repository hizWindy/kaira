"""Kaira profile command group — route profiling and latency measurement.

Uses httpx.AsyncClient with asyncio.run(). Measures p50/p95/p99 latency
and displays results in a Rich table. Never stores or echoes auth tokens.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

app = typer.Typer(help="Route profiling and latency measurement.")

_BASE_URL = "http://127.0.0.1:8000"
_RESULTS_FILE = Path(".kaira") / "profile_results.json"
_SERVER_DOWN_MSG = (
    "⏸️ Server not running.\nStart it with: [bold cyan]kaira run[/bold cyan]"
)


async def _run_profile(method: str, route: str, samples: int = 10) -> list[float]:
    """Execute multiple HTTP requests and collect latency samples.

    Args:
        method: HTTP method.
        route: Route path.
        samples: Number of requests to send.

    Returns:
        List of response times in milliseconds.
    """
    import httpx

    url = f"{_BASE_URL}{route}"
    times: list[float] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(samples):
            start = time.perf_counter()
            try:
                await client.request(method.upper(), url)
            except httpx.ConnectError:
                raise
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
    return times


@app.command("run")
def profile_run(
    method: Annotated[str, typer.Argument(help="HTTP method: GET, POST, etc.")],
    route: Annotated[str, typer.Argument(help="Route path, e.g. /users")],
    samples: Annotated[
        int, typer.Option("--samples", "-n", help="Number of requests")
    ] = 10,
) -> None:
    """Profile a route by sending N requests and measuring latency.

    Results are saved to .kaira/profile_results.json for use with
    'kaira profile report'.

    Args:
        method: HTTP method.
        route: Route path.
        samples: Number of sample requests to send.
    """
    console.print(
        f"[cyan]Profiling {method.upper()} {route} ({samples} requests)...[/cyan]"
    )

    try:
        times = asyncio.run(_run_profile(method, route, samples))
    except ImportError:
        console.print("[red]❌ httpx not installed. Run: pip install httpx[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        if "ConnectError" in type(exc).__name__ or "Connect" in str(exc):
            console.print(Panel(_SERVER_DOWN_MSG, border_style="yellow"))
        else:
            console.print(f"[red]❌ Error: {type(exc).__name__}[/red]")
        raise typer.Exit(1)

    if not times:
        console.print("[red]❌ No successful responses.[/red]")
        raise typer.Exit(1)

    sorted_times = sorted(times)
    avg = statistics.mean(times)
    p50 = statistics.median(times)
    p95 = sorted_times[int(len(sorted_times) * 0.95)]
    p99 = sorted_times[min(int(len(sorted_times) * 0.99), len(sorted_times) - 1)]
    mn = min(times)
    mx = max(times)

    table = Table(title=f"Profile: {method.upper()} {route}", border_style="cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Samples", str(len(times)))
    table.add_row("Avg", f"{avg:.2f}ms")
    table.add_row("p50 (median)", f"{p50:.2f}ms")
    table.add_row("p95", f"{p95:.2f}ms")
    table.add_row("p99", f"{p99:.2f}ms")
    table.add_row("Min", f"{mn:.2f}ms")
    table.add_row("Max", f"{mx:.2f}ms")
    console.print(table)

    # Save results for report command
    _RESULTS_FILE.parent.mkdir(exist_ok=True)
    _RESULTS_FILE.write_text(
        json.dumps({"method": method.upper(), "route": route, "times": times}),
        encoding="utf-8",
    )


@app.command("report")
def profile_report() -> None:
    """Display the last profile run results from .kaira/profile_results.json."""
    if not _RESULTS_FILE.exists():
        console.print(
            "[yellow]No profile results found. Run: kaira profile run <METHOD> <route>[/yellow]"
        )
        return

    try:
        data = json.loads(_RESULTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        console.print("[red]❌ Could not read profile results.[/red]")
        raise typer.Exit(1)

    times: list[float] = data.get("times", [])
    method = data.get("method", "?")
    route = data.get("route", "?")

    if not times:
        console.print("[dim]No timing data in results file.[/dim]")
        return

    sorted_times = sorted(times)
    avg = statistics.mean(times)
    p50 = statistics.median(times)
    p95 = sorted_times[int(len(sorted_times) * 0.95)]
    p99 = sorted_times[min(int(len(sorted_times) * 0.99), len(sorted_times) - 1)]

    table = Table(title=f"Last Profile Report: {method} {route}", border_style="cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Samples", str(len(times)))
    table.add_row("Avg", f"{avg:.2f}ms")
    table.add_row("p50", f"{p50:.2f}ms")
    table.add_row("p95", f"{p95:.2f}ms")
    table.add_row("p99", f"{p99:.2f}ms")
    table.add_row("Min", f"{min(times):.2f}ms")
    table.add_row("Max", f"{max(times):.2f}ms")
    console.print(table)
