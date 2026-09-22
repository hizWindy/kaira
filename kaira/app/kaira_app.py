"""KhairaApp — Framework runtime for Khaira-generated FastAPI projects."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from kaira.config import KairaConfig, get_config
from kaira.app.exceptions import KairaError
from kaira.app.lifecycle import LifecycleManager
from kaira.app.middleware.cors import create_cors_middleware
from kaira.app.middleware.layer_guard import LayerGuardMiddleware
from kaira.app.middleware.rate_limit import RateLimitMiddleware
from kaira.app.middleware.security_headers import SecurityHeadersMiddleware
from kaira.app.providers.base import KairaProvider


NON_RELATIONAL_DB_TYPES = {"mongodb", "atlas", "firebase", "firestore"}


class KairaApp(FastAPI):
    """Framework runtime for Kaira-generated FastAPI projects.

    Key design invariants:
    - Inherits from FastAPI for 100% native FastAPI compatibility.
    - Fully self-contained: never imports from kaira.commands (prevents circular imports).
    - Stateless at class-level: all state isolated to instance attributes.
    - Automated 5-layer pipeline management, router auto-registration, and lifecycle hooks.
    """

    def __init__(
        self,
        project_name: Optional[str] = None,
        config_path: str = ".kaira.json",
        tier: str = "standard",
        auto_register: bool = True,
        enforce_layers: bool = True,
        providers: Optional[List[str]] = None,
        routers_dir: Optional[Path] = None,
        models_dir: Optional[Path] = None,
        lifespan: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        cfg = self._load_project_config(config_path)
        self.config: KairaConfig = cfg
        self.project_name: str = project_name or cfg.db_name or "kaira-project"
        self.tier: str = getattr(cfg, "tier", tier)
        self.auto_register: bool = getattr(cfg, "auto_register", auto_register)
        self.enforce_layers: bool = getattr(cfg, "enforce_layers", enforce_layers)
        self.routers_path: Path = Path(routers_dir) if routers_dir else Path(
            getattr(cfg, "routers_dir", "routers")
        )
        self.models_path: Path = Path(models_dir) if models_dir else Path(
            getattr(cfg, "models_dir", "models")
        )

        # Set default OpenAPI metadata if not provided
        kwargs.setdefault("title", self.project_name.replace("-", " ").title())
        kwargs.setdefault("version", getattr(cfg, "kaira_version", "0.2.0"))

        self.providers: List[KairaProvider] = []
        self._registered_routers: List[Any] = []
        self._registered_models: List[Any] = []
        self._lazy_registered: bool = False
        self._registration_lock: asyncio.Lock = asyncio.Lock()
        self._lifecycle: LifecycleManager = LifecycleManager()

        # Wrap lifespan
        user_lifespan = lifespan
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def framework_lifespan(app_instance: FastAPI):
            # Resolve db_mode state if available
            try:
                from core.db_mode import resolve_binding

                binding = resolve_binding()
                self.state.db_engine_name = binding.engine
                self.state.db_name = binding.db_name
                self.state.db_mode = binding.mode
            except Exception:
                pass

            await self._lifecycle.run_startup()
            for provider in self.providers:
                await provider.startup()

            # Initialize database in dev if core.database is present
            await self._init_database()

            if user_lifespan:
                async with user_lifespan(app_instance):
                    yield
            else:
                yield
            for provider in self.providers:
                await provider.shutdown()
            await self._lifecycle.run_shutdown()

        super().__init__(lifespan=framework_lifespan, **kwargs)

        # Wire framework layers
        self._apply_middleware()
        self._setup_system_routes()

        # Eagerly auto-register routers and models at boot
        if self.auto_register:
            self._register_routers()
            self._register_models()

        # Initialize configured providers
        configured_providers = (
            providers or getattr(cfg, "providers", None) or ["cache", "auth"]
        )
        for p_name in configured_providers:
            self._register_provider_by_name(p_name)

    def _load_project_config(self, config_path: str) -> KairaConfig:
        p = Path(config_path)
        if p.exists():
            try:
                import json

                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return KairaConfig.from_dict(data)
            except Exception:
                pass
        return get_config()

    # ── Provider Subsystem ────────────────────────────────────────────────────

    def register_provider(self, provider: KairaProvider) -> None:
        """Register a provider and bind it to the application runtime."""
        provider.register(self)
        self.providers.append(provider)

    def _register_provider_by_name(self, name: str) -> None:
        """Instantiate and register a built-in provider by name."""
        from kaira.app.providers import get_provider

        try:
            prov = get_provider(name)
            self.register_provider(prov)
        except Exception:
            pass  # Provider optional or dependency uninstalled

    # ── Lifecycle Hooks ───────────────────────────────────────────────────────

    def register_lifecycle_hook(self, event: str, func: Callable[[], Any]) -> None:
        """Register a startup or shutdown lifecycle hook."""
        ev = event.lower()
        if ev in ("startup", "start"):
            self._lifecycle.on_startup(func)
        elif ev in ("shutdown", "stop"):
            self._lifecycle.on_shutdown(func)
        else:
            raise ValueError(
                f"Unknown lifecycle event: {event!r}. Expected 'startup' or 'shutdown'."
            )

    def on_startup(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Decorator to register a startup hook."""
        self.register_lifecycle_hook("startup", func)
        return func

    def on_shutdown(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Decorator to register a shutdown hook."""
        self.register_lifecycle_hook("shutdown", func)
        return func

    # ── Router Registration ───────────────────────────────────────────────────

    def register_router(self, router: Any, prefix: str = "", **kwargs: Any) -> None:
        """Explicitly register an APIRouter instance with the application."""
        self.include_router(router, prefix=prefix or "", **kwargs)
        self._registered_routers.append(router)

    # ── Built-in System Routes ────────────────────────────────────────────────

    def _setup_system_routes(self) -> None:
        """Provide default root and /health endpoints if not overridden by routers."""
        @self.get("/", tags=["system"], summary="Root status", include_in_schema=False)
        async def _root() -> dict[str, Any]:
            return {
                "status": "online",
                "app": self.project_name,
                "version": getattr(self, "version", "0.1.0"),
                "tier": self.tier,
            }

        @self.get("/health", tags=["system"], summary="Health status", include_in_schema=True)
        async def _health() -> dict[str, Any]:
            db_state = {
                "engine": getattr(self.state, "db_engine_name", getattr(self.config, "db_type", "unknown")),
                "name": getattr(self.state, "db_name", getattr(self.config, "db_name", "")),
                "mode": getattr(self.state, "db_mode", "online"),
            }
            return {
                "status": "ok",
                "app": self.project_name,
                "version": getattr(self, "version", "0.1.0"),
                "database": db_state,
            }

    # ── Middleware Pipeline ───────────────────────────────────────────────────

    def _apply_middleware(self) -> None:
        """Wire standard framework middleware in order of execution."""
        # 1. Security Headers
        self.add_middleware(SecurityHeadersMiddleware)

        # 2. CORS
        cors_cls, cors_kwargs = create_cors_middleware()
        self.add_middleware(cors_cls, **cors_kwargs)  # type: ignore[arg-type]

        # 3. Rate limiting
        self.add_middleware(RateLimitMiddleware)

        # 4. Layer Guard (enforce router cannot bypass service to repo)
        self.add_middleware(
            LayerGuardMiddleware,
            routers_dir=self.routers_path,
            enforce=self.enforce_layers,
        )

        # 5. Global Exception Handler
        @self.exception_handler(Exception)
        async def global_exception_handler(
            request: Request, exc: Exception
        ) -> JSONResponse:
            from kaira.app.exceptions import LayerViolationError

            if isinstance(exc, LayerViolationError):
                raise exc
            if isinstance(exc, KairaError):
                return JSONResponse(status_code=400, content={"detail": str(exc)})
            return JSONResponse(
                status_code=500,
                content={"detail": "An internal server error occurred."},
            )

    # ── Auto-Registration Subsystem ───────────────────────────────────────────

    def _setup_lazy_registration(self) -> None:
        """Retained for compatibility. Eager registration in __init__ is now default."""
        pass

    def _register_routers(self) -> None:
        """Scan project routers directory and register any found APIRouters."""
        cwd = Path.cwd()
        routers_dir = self.routers_path if self.routers_path.is_absolute() else cwd / self.routers_path
        if not routers_dir.exists():
            return

        api_prefix = getattr(self.config, "api_prefix", "") or "/api/v1"

        for r_file in sorted(routers_dir.rglob("*.py")):
            if r_file.name.startswith("__"):
                continue
            router_obj = self._import_module_attr(r_file, "router")
            if router_obj is not None and router_obj not in self._registered_routers:
                existing_prefix = getattr(router_obj, "prefix", "")
                stem = r_file.stem.replace("_router", "").replace("router_", "")
                if existing_prefix:
                    # Router already defines its own sub-prefix e.g. /users
                    if not existing_prefix.startswith(api_prefix) and stem not in ("health", "root", "probe", "probes"):
                        prefix = api_prefix
                    else:
                        prefix = ""
                else:
                    # No prefix defined on router
                    if stem in ("health", "root", "probe", "probes"):
                        prefix = ""
                    else:
                        prefix = f"{api_prefix}/{stem}s" if stem else api_prefix

                self.include_router(router_obj, prefix=prefix)
                self._registered_routers.append(router_obj)

    def _register_models(self) -> None:
        """Scan project models directory and import definitions for ORM/ODM registration."""
        cwd = Path.cwd()
        models_dir = self.models_path if self.models_path.is_absolute() else cwd / self.models_path
        if not models_dir.exists():
            return

        for m_file in sorted(models_dir.rglob("*.py")):
            if m_file.name.startswith("__"):
                continue
            self._import_module_attr(m_file, None)

    def _import_module_attr(self, file_path: Path, attr_name: Optional[str]) -> Any:
        """Dynamically load module from file and optionally return an attribute."""
        cwd = Path.cwd()
        cwd_str = str(cwd)
        if cwd_str not in sys.path:
            sys.path.insert(0, cwd_str)

        mod_name = f"_kaira_dyn_{file_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                if attr_name:
                    return getattr(mod, attr_name, None)
                return mod
        except Exception as exc:
            import logging

            logging.getLogger("kaira.app").debug(f"Failed to dynamically import {file_path}: {exc}")
            return None
        return None

    # ── Database Migration & Init ─────────────────────────────────────────────

    async def _init_database(self) -> None:
        """Initialize database schema or document models at application boot."""
        try:
            import importlib

            try:
                db_mod = importlib.import_module("core.database")
            except ImportError:
                return

            if hasattr(db_mod, "init_db"):
                # MongoDB / Beanie
                await db_mod.init_db()
            elif hasattr(db_mod, "create_tables"):
                # SQLAlchemy async in development mode
                import os

                if os.getenv("APP_ENV", "development") == "development":
                    await db_mod.create_tables()
        except Exception as exc:
            import logging

            logging.getLogger("kaira.app").debug(f"Database initialization skipped or deferred: {exc}")

    def _run_migrations(self) -> None:
        """Run Alembic migrations on startup in production mode."""
        if getattr(self.config, "db_type", "sqlite") in NON_RELATIONAL_DB_TYPES:
            return
        try:
            from alembic import command
            from alembic.config import Config

            if Path("alembic.ini").exists():
                alembic_cfg = Config("alembic.ini")
                command.upgrade(alembic_cfg, "head")
        except Exception:
            pass

    # ── Server Launcher ───────────────────────────────────────────────────────

    def run(
        self, dev: bool = True, host: str = "0.0.0.0", port: int = 8000, **kwargs: Any
    ) -> None:
        """Start the framework application server via Uvicorn."""
        import uvicorn

        if not dev:
            self._run_migrations()

        target_app = "main:app" if Path("main.py").exists() else self

        uvicorn_kwargs: Dict[str, Any] = {
            "app": target_app,
            "host": host,
            "port": port,
            "reload": dev,
        }
        if dev and target_app == "main:app":
            uvicorn_kwargs["reload_includes"] = [
                "*.py",
                "routers/**/*.py",
                "models/**/*.py",
                "schemas/**/*.py",
                "services/**/*.py",
            ]

        uvicorn_kwargs.update(kwargs)
        uvicorn.run(**uvicorn_kwargs)
