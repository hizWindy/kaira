"""API audit command group."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from devflow.config import get_config
from devflow.console import console

app = typer.Typer(help="API auditing and security checking commands.")


@app.command("routes")
def audit_routes() -> None:
    """List all project endpoints and their handlers."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    routers_dir = output_root / config.routers_dir
    if not routers_dir.exists():
        console.print("[yellow]No routers directory found.[/yellow]")
        return

    table = Table(title="DevFlow — Registered API Routes", border_style="cyan")
    table.add_column("Router", justify="left")
    table.add_column("Method", justify="left")
    table.add_column("Path", justify="left")
    table.add_column("Handler Function", justify="left")

    for f in routers_dir.glob("*_router.py"):
        content = f.read_text(encoding="utf-8")
        # Find APIRouter decorators, e.g. @router.get("/", ...)
        # Parse def handlers
        endpoints = re.findall(
            r"@(router\.(get|post|put|delete|patch|websocket))\(\s*\"([^\"]+)\"[^)]*\)\s*(?:@[^\n]+\s*)*(?:async\s+)?def\s+(\w+)",
            content,
            re.MULTILINE
        )
        for _, method, path, handler in endpoints:
            table.add_row(f.name, method.upper(), path, handler)

    console.print(table)


@app.command("security")
def audit_security() -> None:
    """Check routes, schemas, models, and environments for security issues."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    issues = []
    checked_routes = 0
    passed_routes = 0

    # 1. Audit Router files for auth guards & rate limits
    routers_dir = output_root / config.routers_dir
    if routers_dir.exists():
        for f in routers_dir.glob("*_router.py"):
            content = f.read_text(encoding="utf-8")
            # Parse route functions
            endpoints = re.findall(
                r"@(router\.(get|post|put|delete|patch|websocket))\(\s*\"([^\"]+)\"[^)]*\)\s*(?:@[^\n]+\s*)*(?:async\s+)?def\s+(\w+)",
                content,
                re.MULTILINE
            )
            # Find function body blocks to check for Depends and limiter
            for deco, method, path, handler in endpoints:
                checked_routes += 1
                route_issues = []
                
                # Check for auth guards
                func_pattern = rf"(def\s+{handler}\(.*?\)\s*->\s*.*?:)"
                func_match = re.search(func_pattern, content, re.DOTALL)
                if func_match:
                    func_sig = func_match.group(1)
                    if "get_current_user" not in func_sig and "validate_api_key" not in func_sig:
                        # Exclude auth route itself
                        if "auth" not in path:
                            route_issues.append("No auth guard")
                else:
                    # Generic check
                    if "get_current_user" not in content and "validate_api_key" not in content and "auth" not in path:
                         route_issues.append("No auth guard")

                # Check for rate limits
                # Find if @limiter.limit decoration sits above the def
                block_pattern = rf"(@limiter\.limit\(.*?\)\s*)*@router\.{method}\(.*?\)\s*(?:@limiter\.limit\(.*?\)\s*)*(?:async\s+)?def\s+{handler}"
                limit_match = re.search(block_pattern, content, re.DOTALL)
                if not limit_match or "@limiter.limit" not in limit_match.group(0):
                     route_issues.append("No rate limit")

                if route_issues:
                    issues.append((f"{path} ({method.upper()})", ", ".join(route_issues), "❌ High" if "auth" in "".join(route_issues) else "⚠️  Medium"))
                else:
                    passed_routes += 1

    # 2. Audit Schemas for password exposures
    schemas_dir = output_root / config.schemas_dir
    if schemas_dir.exists():
        for f in schemas_dir.glob("*_schema.py"):
            content = f.read_text(encoding="utf-8")
            if "class" in content and "Response" in content:
                # Find response schemas
                resp_schema = re.search(r"class\s+\w+Response\(.*?\):(.*?)class", content + "\nclass", re.DOTALL)
                if resp_schema:
                    body = resp_schema.group(1)
                    if "password" in body:
                        issues.append((f.name, "Exposes password in Response schema", "❌ High"))
                    if "id: int" in body:
                        issues.append((f.name, "Exposes auto-increment id in Response schema", "⚠️  Medium"))

    # 3. Audit Environment files
    envs = ["development", "staging", "production"]
    gitignore_path = output_root / ".gitignore"
    gitignore_exists = gitignore_path.exists()
    gi_content = gitignore_path.read_text(encoding="utf-8") if gitignore_exists else ""
    
    if gitignore_exists:
        if ".env" not in gi_content and ".env.*" not in gi_content:
            issues.append((".gitignore", ".env files are not added to .gitignore", "❌ High"))
    else:
        issues.append((".gitignore", ".gitignore file is missing", "❌ High"))

    for env_name in envs:
        env_path = output_root / f".env.{env_name}"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            env_keys = {}
            for line in content.split("\n"):
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_keys[k.strip()] = v.strip()

            secret = env_keys.get("JWT_SECRET_KEY", "")
            if secret and len(secret) < 32:
                issues.append((f".env.{env_name}", "JWT_SECRET_KEY is shorter than 32 chars", "❌ High"))
                
            debug = env_keys.get("DEBUG", "False").lower() == "true"
            if env_name == "production" and debug:
                issues.append((f".env.{env_name}", "DEBUG is enabled in production environment", "❌ High"))

            origins = env_keys.get("ALLOWED_ORIGINS", "")
            if env_name == "production" and "*" in origins:
                 issues.append((f".env.{env_name}", "CORS wildcard '*' is allowed in production", "❌ High"))

    # Print results
    table = Table(title="DevFlow Security Audit", border_style="cyan")
    table.add_column("Route / Asset", justify="left")
    table.add_column("Issue Detected", justify="left")
    table.add_column("Severity", justify="right")

    for asset, msg, sev in issues:
        table.add_row(asset, msg, sev)

    console.print(table)

    # Calculate Security Score
    # Starting score = 100
    # Subtract 15 for each High issue, 5 for each Medium issue
    score = 100
    for _, _, sev in issues:
        if "High" in sev:
            score -= 15
        elif "Medium" in sev:
            score -= 5
    score = max(0, score)

    score_color = "green" if score >= 80 else ("yellow" if score >= 60 else "red")
    console.print(f"\n[bold]Security Score: [{score_color}]{score}/100[/{score_color}][/bold]")


@app.command("unused")
def audit_unused() -> None:
    """Detect generated files/routers that are not referenced in the application."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    main_app_path = output_root / "main.py"
    if not main_app_path.exists():
        console.print("[red]main.py not found.[/red]")
        return

    main_content = main_app_path.read_text(encoding="utf-8")

    routers_dir = output_root / config.routers_dir
    unused = []

    if routers_dir.exists():
        for f in routers_dir.glob("*_router.py"):
            router_name = f.stem
            # Check if router is imported or registered in main.py
            if router_name not in main_content:
                unused.append(f"{config.routers_dir}/{f.name}")

    table = Table(title="DevFlow — Unused Generated Assets", border_style="yellow")
    table.add_column("Asset Path", justify="left")
    table.add_column("Status", justify="left")

    for asset in unused:
        table.add_row(asset, "❌ Unregistered (not found in main.py)")

    if unused:
        console.print(table)
    else:
        console.print("[green]✔ No unused generated assets found. All registered in main.py![/green]")
