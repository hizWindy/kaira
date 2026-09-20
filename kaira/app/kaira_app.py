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
        lifespan: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        cfg = self._load_project_config(config_path)
        self.config: KairaConfig = cfg
        self.project_name: str = project_name or cfg.db_name or "kaira-project"
        self.tier: str = getattr(cfg, "tier", tier)
        self.auto_register: bool = getattr(cfg, "auto_register", auto_register)
        self.enforce_layers: bool = getattr(cfg, "enforce_layers", enforce_layers)
        self.routers_path: Path = routers_dir or Path(
            getattr(cfg, "routers_dir", "routers")
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
            await self._lifecycle.run_startup()
            for provider in self.providers:
                await provider.startup()
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
        if self.auto_register:
            self._setup_lazy_registration()

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

    # ── Router Registration ───────────────────────────────────────────────────

    def register_router(self, router: Any, prefix: str = "", **kwargs: Any) -> None:
        """Explicitly register an APIRouter instance with the application."""
        self.include_router(router, prefix=prefix or "", **kwargs)
        self._registered_routers.append(router)

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
        """Register routers and models on the first incoming HTTP request."""

        @self.middleware("http")
        async def lazy_registration_middleware(
            request: Request, call_next: Callable[[Request], Any]
        ) -> Any:
            if not self._lazy_registered:
                async with self._registration_lock:
                    if not self._lazy_registered:
                        await self._register_routers()
                        await self._register_models()
                        self._lazy_registered = True
            return await call_next(request)

    async def _register_routers(self) -> None:
        """Scan project routers directory and register any found APIRouters."""
        cwd = Path.cwd()
        r_dir_name = getattr(self.config, "routers_dir", "routers")
        routers_dir = cwd / r_dir_name
        if not routers_dir.exists():
            return

        for r_file in routers_dir.rglob("*.py"):
            if r_file.name.startswith("__"):
                continue
            router_obj = self._import_module_attr(r_file, "router")
            if router_obj is not None and router_obj not in self._registered_routers:
                # Derive endpoint prefix e.g. /users from user_router.py
                stem = r_file.stem.replace("_router", "").replace("router_", "")
                prefix = f"/{stem}" if stem else ""
                self.include_router(router_obj, prefix=prefix)
                self._registered_routers.append(router_obj)

    async def _register_models(self) -> None:
        """Scan project models directory and import definitions for ORM/ODM registration."""
        cwd = Path.cwd()
        m_dir_name = getattr(self.config, "models_dir", "models")
        models_dir = cwd / m_dir_name
        if not models_dir.exists():
            return

        for m_file in models_dir.rglob("*.py"):
            if m_file.name.startswith("__"):
                continue
            self._import_module_attr(m_file, None)

    def _import_module_attr(self, file_path: Path, attr_name: Optional[str]) -> Any:
        """Dynamically load module from file and optionally return an attribute."""
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
        except Exception:
            return None
        return None

    # ── Database Migration Auto-Run ───────────────────────────────────────────

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

        uvicorn_kwargs: Dict[str, Any] = {
            "app": self,
            "host": host,
            "port": port,
            "reload": dev,
        }
        if dev:
            uvicorn_kwargs["reload_includes"] = ["*.py", "app/**/*.py"]

        uvicorn_kwargs.update(kwargs)
        uvicorn.run(**uvicorn_kwargs)
