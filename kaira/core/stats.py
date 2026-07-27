"""Database statistics collection shared by `kaira db info` and post-seed summaries.

One code path inspects both paradigms so the two surfaces cannot drift: rows are
normalised to ``{"name", "count", ...}`` regardless of whether they came from a
SQL inspector or a Mongo collection listing.
"""

from __future__ import annotations

import asyncio
from typing import Any

from rich.table import Table

from pathlib import Path
from urllib.parse import urlsplit

from kaira.config import get_config
from kaira.core.drivers import get_engine_driver


def db_name_from_url(url: str, default: str = "") -> str:
    """Extract the database name from a connection URL.

    Args:
        url: Connection URL or DSN.
        default: Value to return when the URL carries no database name.

    Returns:
        The database name, or fallback from config / ``default`` when absent.
    """
    if url:
        try:
            parsed = urlsplit(url)
            path = parsed.path.lstrip("/")
            if path:
                raw_name = path.split("?")[0]
                if raw_name:
                    cleaned = Path(raw_name).name if ("/" in raw_name or "\\" in raw_name or raw_name.endswith(".db")) else raw_name
                    if cleaned:
                        return cleaned
        except Exception:
            pass

    try:
        config = get_config()
        if config and hasattr(config, "project_name") and config.project_name:
            return config.project_name
    except Exception:
        pass

    return default or "kaira_db"


async def _collect_document_stats(url: str) -> tuple[str, list[dict[str, Any]]]:
    """Collect collection names and document counts from MongoDB."""
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=3000)
    try:
        name = db_name_from_url(url, "admin")
        db = client[name]
        rows: list[dict[str, Any]] = []
        for coll in sorted(await db.list_collection_names()):
            rows.append({"name": coll, "count": await db[coll].count_documents({})})
        return name, rows
    finally:
        client.close()


async def _collect_relational_stats(url: str) -> tuple[str, list[dict[str, Any]]]:
    """Collect table names, column counts, and row counts from a SQL database."""
    from sqlalchemy.ext.asyncio import create_async_engine

    def _inspect(sync_conn) -> list[dict[str, Any]]:
        from sqlalchemy import inspect, text

        inspector = inspect(sync_conn)
        rows: list[dict[str, Any]] = []
        for table in sorted(inspector.get_table_names()):
            columns = inspector.get_columns(table)
            try:
                count = sync_conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            except Exception:
                count = 0
            rows.append({"name": table, "columns": len(columns), "count": count or 0})
        return rows

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            rows = await conn.run_sync(_inspect)
    finally:
        await engine.dispose()

    return db_name_from_url(url, "local"), rows


def collect_db_stats(db_type: str, url: str) -> tuple[str, list[dict[str, Any]]]:
    """Collect table/collection statistics for either database paradigm.

    Args:
        db_type: Configured database type (e.g. ``postgresql``, ``mongodb``).
        url: Connection URL.

    Returns:
        Tuple of ``(db_name, rows)`` where each row has ``name`` and ``count``
        keys, plus ``columns`` for relational databases.

    Raises:
        Exception: Any driver-level connection or query failure, for the caller
            to render.
    """
    driver = get_engine_driver(db_type)
    coro = (
        _collect_document_stats(url)
        if driver.is_document_db
        else _collect_relational_stats(url)
    )

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def try_collect_db_stats(db_type: str, url: str) -> tuple[str, list[dict[str, Any]]] | None:
    """Best-effort :func:`collect_db_stats` that returns ``None`` on failure.

    Used where statistics are a convenience rather than the command's purpose —
    a summary that cannot be gathered must not fail the operation it describes.
    """
    try:
        return collect_db_stats(db_type, url)
    except Exception:
        return None


def counts_by_name(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Reduce stats rows to a ``{name: count}`` map for delta comparisons."""
    return {row["name"]: row.get("count", 0) for row in rows}


def build_stats_table(
    db_type: str,
    db_name: str,
    rows: list[dict[str, Any]],
    before: dict[str, int] | None = None,
    title: str | None = None,
) -> Table:
    """Render stats rows as a Rich table, optionally showing a change column.

    Args:
        db_type: Configured database type, selecting the column layout.
        db_name: Database name, shown in the title.
        rows: Stats rows from :func:`collect_db_stats`.
        before: Prior ``{name: count}`` map. When given, a Change column shows
            the delta for each entity.
        title: Override for the table title.

    Returns:
        A populated Rich table.
    """
    is_doc = get_engine_driver(db_type).is_document_db
    entity = "Collection" if is_doc else "Table"
    unit = "Documents" if is_doc else "Rows"

    table = Table(
        title=title or f"⚡ Kaira — Database Info ({db_type.upper()}: [cyan]{db_name}[/cyan])",
        border_style="cyan",
    )
    table.add_column(entity, style="bold cyan")
    if not is_doc:
        table.add_column("Columns", justify="right", style="yellow")
    table.add_column(unit, justify="right", style="green")
    if before is not None:
        table.add_column("Change", justify="right", style="magenta")

    for row in rows:
        cells = [row["name"]]
        if not is_doc:
            cells.append(str(row.get("columns", 0)))
        cells.append(str(row.get("count", 0)))
        if before is not None:
            delta = row.get("count", 0) - before.get(row["name"], 0)
            if delta > 0:
                cells.append(f"[green]+{delta}[/green]")
            elif delta < 0:
                cells.append(f"[red]{delta}[/red]")
            else:
                cells.append("[dim]—[/dim]")
        table.add_row(*cells)

    return table
