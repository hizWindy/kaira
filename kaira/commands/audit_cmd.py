"""API audit command group."""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.config import get_config
from kaira.console import console

app = typer.Typer(help="API auditing and security checking commands.")


@app.command("routes")
def audit_routes() -> None:
    """List all project endpoints with full paths, auth, and rate-limit details."""
    from rich import box

    from kaira.core.theme import Theme, sym

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    routers_dir = output_root / config.routers_dir

    if not routers_dir.exists():
        console.print(
            Panel(
                f"[{Theme.WARNING}]{sym('WARN')}  No routers directory found at "
                f"[bold]{routers_dir}[/bold]\n"
                f"[dim]Run [bold]kaira generate model <Name>[/bold] to scaffold your first router.[/dim]",
                border_style=Theme.BORDER_WARNING,
                title="[bold]kaira audit routes[/bold]",
            )
        )
        return

    router_files = sorted(routers_dir.glob("*_router.py"))
    if not router_files:
        console.print(
            f"[{Theme.MUTED}]No router files found in {routers_dir}[/{Theme.MUTED}]"
        )
        return

    api_version = getattr(config, "api_version", "v1")
    api_prefix = f"/api/{api_version}"

    METHOD_COLORS = {
        "GET": "bold green",
        "POST": "bold blue",
        "PUT": "bold yellow",
        "PATCH": "bold magenta",
        "DELETE": "bold red",
        "WEBSOCKET": "bold cyan",
    }

    table = Table(
        title=f"[bold {Theme.PRIMARY}]Khaira — API Route Audit[/bold {Theme.PRIMARY}]  "
        f"[dim]{api_prefix}/*[/dim]",
        box=box.ROUNDED,
        border_style=Theme.BORDER_PRIMARY,
        header_style=f"bold {Theme.PRIMARY}",
        show_lines=True,
        expand=False,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Method", width=9, justify="center")
    table.add_column("Full Route", style=f"bold {Theme.PRIMARY}", min_width=30)
    table.add_column("Handler", style="cyan", min_width=18)
    table.add_column("Auth", width=13, justify="center")
    table.add_column("Rate Limit", style=Theme.MUTED, width=12, justify="center")
    table.add_column("File", style=Theme.MUTED, min_width=16)

    http_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "WEBSOCKET"]
    row_num = 0
    total = 0
    secured = 0
    rate_limited = 0

    for f in router_files:
        content = f.read_text(encoding="utf-8")
        lines = content.split("\n")

        # Parse router prefix
        prefix_match = re.search(r"prefix\s*=\s*[\"']([^\"']+)[\"']", content)
        router_prefix = prefix_match.group(1) if prefix_match else ""
        if router_prefix and not router_prefix.startswith("/"):
            router_prefix = "/" + router_prefix

        current_rate_limit = None

        for idx, line in enumerate(lines):
            line_str = line.strip()

            # Capture rate limit decorator
            limit_m = re.match(r"@limiter\.limit\(([^)]+)\)", line_str)
            if limit_m:
                val = limit_m.group(1).strip("\"' ")
                if "RATE_LIMIT_GET" in val:
                    current_rate_limit = "60/min"
                elif "RATE_LIMIT_WRITE" in val:
                    current_rate_limit = "20/min"
                else:
                    current_rate_limit = val.replace("/minute", "/min")
                continue

            for method in http_methods:
                ml = method.lower()

                # Single-line: @router.get("/path", ...)
                single = re.match(rf"@router\.{ml}\(\s*[\"']([^\"']*)[\"']", line_str)

                sub_path = None
                handler = None

                if single:
                    sub_path = single.group(1)
                elif re.match(rf"@router\.{ml}\(\s*$", line_str):
                    # Multi-line: path is on the next non-empty line
                    for off in range(1, 6):
                        if idx + off < len(lines):
                            nxt = lines[idx + off].strip()
                            pm = re.match(r"""[\"']([^\"']*)[\"']""", nxt)
                            if pm:
                                sub_path = pm.group(1)
                                break
                    if sub_path is None:
                        continue
                else:
                    continue

                # Normalise sub_path
                if sub_path == "/":
                    sub_path = ""
                elif sub_path and not sub_path.startswith("/"):
                    sub_path = "/" + sub_path

                full_route = re.sub(
                    r"/+", "/", f"{api_prefix}{router_prefix}{sub_path}"
                )

                # Find the handler function name
                for off in range(1, 20):
                    if idx + off < len(lines):
                        fn_m = re.match(
                            r"(?:async\s+)?def\s+(\w+)\s*\(", lines[idx + off].strip()
                        )
                        if fn_m:
                            handler = fn_m.group(1)
                            # Check auth in function signature
                            sig_lines = []
                            for so in range(12):
                                if idx + off + so < len(lines):
                                    sig_lines.append(lines[idx + off + so])
                                    if "):" in lines[idx + off + so]:
                                        break
                            sig_str = "".join(sig_lines)
                            has_auth = (
                                "get_current_user" in sig_str
                                or "validate_api_key" in sig_str
                            )
                            break

                if handler is None:
                    has_auth = False

                # Build display strings
                mcolor = METHOD_COLORS.get(method, "white")
                method_str = f"[{mcolor}]{method}[/{mcolor}]"

                auth_str = (
                    f"[bold green]{sym('LOCK')} Secured[/bold green]"
                    if has_auth
                    else f"[dim red]{sym('WARN')} Public[/dim red]"
                )

                rl_display = current_rate_limit or "[dim]—[/dim]"
                rl_str = (
                    f"[{Theme.MUTED}]{rl_display}[/{Theme.MUTED}]"
                    if current_rate_limit
                    else rl_display
                )

                row_num += 1
                table.add_row(
                    str(row_num),
                    method_str,
                    full_route,
                    handler or "?",
                    auth_str,
                    rl_str,
                    f.name,
                )

                total += 1
                if has_auth:
                    secured += 1
                if current_rate_limit:
                    rate_limited += 1

                current_rate_limit = None
                break

    console.print()
    console.print(table)

    # Summary footer
    unsecured = total - secured
    sec_color = (
        Theme.SUCCESS
        if unsecured == 0
        else Theme.WARNING
        if unsecured <= 2
        else Theme.ERROR
    )
    rl_color = Theme.SUCCESS if rate_limited == total else Theme.WARNING

    summary = (
        f"  [{Theme.MUTED}]Total routes :[/{Theme.MUTED}]  [bold]{total}[/bold]\n"
        f"  [{Theme.MUTED}]Secured      :[/{Theme.MUTED}]  [{sec_color}]{secured}/{total}[/{sec_color}]\n"
        f"  [{Theme.MUTED}]Rate-limited :[/{Theme.MUTED}]  [{rl_color}]{rate_limited}/{total}[/{rl_color}]\n"
        f"  [{Theme.MUTED}]API prefix   :[/{Theme.MUTED}]  [bold cyan]{api_prefix}[/bold cyan]"
    )
    console.print(
        Panel(
            summary,
            title="[bold]Audit Summary[/bold]",
            border_style=Theme.BORDER_PRIMARY,
            padding=(0, 2),
        )
    )
    console.print()


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
                re.MULTILINE,
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
                    if (
                        "get_current_user" not in func_sig
                        and "validate_api_key" not in func_sig
                    ):
                        # Exclude auth route itself
                        if "auth" not in path:
                            route_issues.append("No auth guard")
                else:
                    # Generic check
                    if (
                        "get_current_user" not in content
                        and "validate_api_key" not in content
                        and "auth" not in path
                    ):
                        route_issues.append("No auth guard")

                # Check for rate limits
                # Find if @limiter.limit decoration sits above the def
                block_pattern = rf"(@limiter\.limit\(.*?\)\s*)*@router\.{method}\(.*?\)\s*(?:@limiter\.limit\(.*?\)\s*)*(?:async\s+)?def\s+{handler}"
                limit_match = re.search(block_pattern, content, re.DOTALL)
                if not limit_match or "@limiter.limit" not in limit_match.group(0):
                    route_issues.append("No rate limit")

                if route_issues:
                    issues.append(
                        (
                            f"{path} ({method.upper()})",
                            ", ".join(route_issues),
                            "❌ High"
                            if "auth" in "".join(route_issues)
                            else "⚠️  Medium",
                        )
                    )
                else:
                    passed_routes += 1

    # 2. Audit Schemas for password exposures
    schemas_dir = output_root / config.schemas_dir
    if schemas_dir.exists():
        for f in schemas_dir.glob("*_schema.py"):
            content = f.read_text(encoding="utf-8")
            if "class" in content and "Response" in content:
                # Find response schemas
                resp_schema = re.search(
                    r"class\s+\w+Response\(.*?\):(.*?)class",
                    content + "\nclass",
                    re.DOTALL,
                )
                if resp_schema:
                    body = resp_schema.group(1)
                    if "password" in body:
                        issues.append(
                            (f.name, "Exposes password in Response schema", "❌ High")
                        )
                    if "id: int" in body:
                        issues.append(
                            (
                                f.name,
                                "Exposes auto-increment id in Response schema",
                                "⚠️  Medium",
                            )
                        )

    # 3. Audit Environment files
    envs = ["development", "staging", "production"]
    gitignore_path = output_root / ".gitignore"
    gitignore_exists = gitignore_path.exists()
    gi_content = gitignore_path.read_text(encoding="utf-8") if gitignore_exists else ""

    if gitignore_exists:
        if ".env" not in gi_content and ".env.*" not in gi_content:
            issues.append(
                (".gitignore", ".env files are not added to .gitignore", "❌ High")
            )
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
                issues.append(
                    (
                        f".env.{env_name}",
                        "JWT_SECRET_KEY is shorter than 32 chars",
                        "❌ High",
                    )
                )

            debug = env_keys.get("DEBUG", "False").lower() == "true"
            if env_name == "production" and debug:
                issues.append(
                    (
                        f".env.{env_name}",
                        "DEBUG is enabled in production environment",
                        "❌ High",
                    )
                )

            origins = env_keys.get("ALLOWED_ORIGINS", "")
            if env_name == "production" and "*" in origins:
                issues.append(
                    (
                        f".env.{env_name}",
                        "CORS wildcard '*' is allowed in production",
                        "❌ High",
                    )
                )

    # Print results
    table = Table(title="Kaira Security Audit", border_style="cyan")
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
    console.print(
        f"\n[bold]Security Score: [{score_color}]{score}/100[/{score_color}][/bold]"
    )


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
    uses_kaira_app = "KairaApp" in main_content or "KhairaApp" in main_content
    auto_register = uses_kaira_app and getattr(config, "auto_register", True)

    routers_dir = output_root / config.routers_dir
    unused = []

    if routers_dir.exists():
        for f in sorted(routers_dir.glob("*_router.py")):
            router_name = f.stem
            # If KairaApp auto-registration is active, all routers in routers_dir are registered
            if not auto_register and router_name not in main_content:
                unused.append(f"{config.routers_dir}/{f.name}")

    table = Table(title="Khaira — Unused Generated Assets", border_style="yellow")
    table.add_column("Asset Path", justify="left")
    table.add_column("Status", justify="left")

    for asset in unused:
        table.add_row(asset, "❌ Unregistered (not found in main.py)")

    if unused:
        console.print(table)
    else:
        status_msg = (
            "[green]✔ No unused generated assets found. All auto-registered in KairaApp![/green]"
            if auto_register
            else "[green]✔ No unused generated assets found. All registered in main.py![/green]"
        )
        console.print(status_msg)
