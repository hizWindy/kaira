"""Kaira integrate command group — third-party service integrations.

Generates integrations/<category>/<provider>/{__init__.py, service.py, schemas.py}.
Installs provider SDK, adds env keys to .env.example and all .env* files,
and adds required fields to settings.py so env validate catches missing values.

Security rules:
- API keys only from settings — never hardcoded or logged
- Provider error details never exposed in HTTP responses
- Provider calls wrapped in try/except with logger.error + re-raise
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Third-party service integrations.")

_PROVIDERS: dict[str, dict[str, tuple[str, list[str]]]] = {
    "email": {
        "sendgrid": ("sendgrid", ["SENDGRID_API_KEY"]),
        "mailgun": ("requests", ["MAILGUN_API_KEY", "MAILGUN_DOMAIN"]),
        "smtp": ("", ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"]),
    },
    "payment": {
        "stripe": ("stripe", ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY"]),
        "paypal": ("paypalrestsdk", ["PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"]),
        "paymongo": ("requests", ["PAYMONGO_SECRET_KEY", "PAYMONGO_PUBLIC_KEY"]),
    },
    "storage": {
        "s3": (
            "boto3",
            [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_REGION",
                "AWS_BUCKET_NAME",
            ],
        ),
        "cloudinary": (
            "cloudinary",
            ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"],
        ),
        "gcs": (
            "google-cloud-storage",
            ["GCS_BUCKET_NAME", "GOOGLE_APPLICATION_CREDENTIALS"],
        ),
    },
    "notify": {
        "firebase": ("firebase-admin", ["FIREBASE_CREDENTIALS_PATH"]),
        "onesignal": ("requests", ["ONESIGNAL_APP_ID", "ONESIGNAL_API_KEY"]),
        "twilio": (
            "twilio",
            ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"],
        ),
    },
    "monitor": {
        "sentry": ("sentry-sdk", ["SENTRY_DSN"]),
        "datadog": ("datadog", ["DATADOG_API_KEY", "DATADOG_APP_KEY"]),
        "newrelic": ("newrelic", ["NEW_RELIC_LICENSE_KEY"]),
    },
    "search": {
        "elasticsearch": ("elasticsearch", ["ELASTICSEARCH_URL"]),
        "meilisearch": ("meilisearch", ["MEILISEARCH_URL", "MEILISEARCH_API_KEY"]),
    },
}


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _update_env_files(key: str, value: str) -> None:
    """Add a key to all .env* files with an empty placeholder."""
    for env_file in Path.cwd().glob(".env*"):
        if env_file.is_dir():
            continue
        try:
            content = env_file.read_text(encoding="utf-8")
            if f"{key}=" not in content:
                content += f"\n{key}={value}\n"
                env_file.write_text(content, encoding="utf-8")
        except OSError:
            pass


def _add_to_settings(key: str) -> None:
    """Add a required field to settings.py so env validate catches it missing."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    for candidate in [
        output_root / "core" / "config.py",
        output_root / "config" / "settings.py",
    ]:
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
            if key not in content:
                content = content.rstrip() + f'\n    {key}: str = ""\n'
                candidate.write_text(content, encoding="utf-8")
            return


def _provider_class_name(provider: str) -> str:
    """Convert provider name to PascalCase class prefix."""
    return provider.replace("-", "_").replace("_", " ").title().replace(" ", "")


@app.command("add")
def integrate_add(
    category: Annotated[
        str,
        typer.Option(
            "--provider",
            help="Provider spec: <category>/<provider>, e.g. email/sendgrid",
        ),
    ],
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Non-interactive: never prompt (CI-friendly)."),
    ] = False,
) -> None:
    """Add a third-party integration."""
    if "/" not in category:
        console.print(
            Panel(
                f"[red]❌ Invalid provider spec '{category}'.\n"
                "Format: --provider <category>/<provider>\n"
                "Example: kaira integrate --provider email/sendgrid[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    cat, prov = category.strip().split("/", 1)
    cat = cat.lower()
    prov = prov.lower()

    if cat not in _PROVIDERS:
        valid_cats = ", ".join(_PROVIDERS.keys())
        console.print(f"[red]❌ Unknown category '{cat}'. Valid: {valid_cats}[/red]")
        raise typer.Exit(1)

    if prov not in _PROVIDERS[cat]:
        valid_provs = ", ".join(_PROVIDERS[cat].keys())
        console.print(
            f"[red]❌ Unknown provider '{prov}' for category '{cat}'. Valid: {valid_provs}[/red]"
        )
        raise typer.Exit(1)

    sdk_package, env_keys = _PROVIDERS[cat][prov]
    class_prefix = _provider_class_name(prov)

    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    integration_dir = output_root / "integrations" / cat / prov
    integration_dir.mkdir(parents=True, exist_ok=True)
    (integration_dir / "__init__.py").touch(exist_ok=True)

    jinja = _get_env_loader()

    service_tmpl = jinja.get_template("integration_service.py.j2")
    service_path = integration_dir / "service.py"
    service_path.write_text(
        service_tmpl.render(
            provider=prov,
            category=cat,
            class_name=class_prefix,
        ),
        encoding="utf-8",
    )
    console.print(f"  [green]✅[/green] Generated: [cyan]{service_path}[/cyan]")

    schema_tmpl = jinja.get_template("integration_schema.py.j2")
    schema_path = integration_dir / "schemas.py"
    schema_path.write_text(
        schema_tmpl.render(
            provider=prov,
            category=cat,
            class_name=class_prefix,
        ),
        encoding="utf-8",
    )
    console.print(f"  [green]✅[/green] Generated: [cyan]{schema_path}[/cyan]")

    for key in env_keys:
        _update_env_files(key, "")
        _add_to_settings(key)
        console.print(f"  [green]✅[/green] Env key added: [yellow]{key}[/yellow]")

    if sdk_package:
        console.print(f"  [cyan]Installing {sdk_package}...[/cyan]")
        from kaira.commands.project import install_packages

        install_packages([sdk_package])

    console.print(
        Panel(
            f"[green]✅ {class_prefix} ({cat}/{prov}) integration generated.[/green]\n"
            "Set these env vars in your .env file:\n"
            + "\n".join(f"  [yellow]{k}[/yellow]=your_value" for k in env_keys),
            border_style="green",
        )
    )

    # Search and monitoring change what Docker should contain — search adds a
    # compose service, monitoring is env wiring only but is still recorded so
    # `kaira docker status` can report it.
    from kaira.config import set_config_values
    from kaira.core.docker_render import maybe_autosync

    if cat == "search":
        set_config_values(search_provider=prov)
    elif cat == "monitor":
        set_config_values(monitor_provider=prov)
        # The generated service.py is generic boilerplate — it never called the
        # provider's init(). This wires the real SDK startup, with a
        # cost-conscious default sample rate, through the standard diff/confirm
        # prompt so main.py is never rewritten silently.
        from kaira.commands.monitor_cmd import wire_provider_sdk

        wire_provider_sdk(output_root, prov, quiet=quiet)
    maybe_autosync(quiet=quiet)


@app.command("list")
def integrate_list() -> None:
    """List all available integration providers by category."""
    table = Table(title="⚡ Kaira — Available Integrations", border_style="cyan")
    table.add_column("Category", style="bold")
    table.add_column("Providers")

    for cat, providers in _PROVIDERS.items():
        table.add_row(cat, ", ".join(providers.keys()))

    console.print(table)
    console.print("[dim]Usage: kaira integrate --provider <category>/<provider>[/dim]")
