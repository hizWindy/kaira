"""Kaira AI command group — RAG, Agents, Sub-Agents, and Skills scaffolding.

Generates production-grade AI infrastructure for both new and existing FastAPI apps:
- Universal multi-provider LLM gateway (OpenAI, Anthropic, Ollama, DeepSeek).
- 5-layer RAG pipelines with vector similarity search (pgvector, MongoDB Atlas).
- Service-as-a-Tool AST introspection (turning Kaira services into Agent Skills).
- Multi-agent LangGraph supervisor workflows.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from kaira.console import console
from kaira.core.detector import write_with_check
from kaira.core.wiring import register_router_in_main
from kaira.core.ai_introspect import introspect_service_file

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Production AI, RAG, Multi-Agent, and Skills scaffolding.")


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower().replace("-", "_")


def _to_pascal(name: str) -> str:
    snake = _to_snake(name)
    return "".join(word.capitalize() for word in snake.split("_") if word)


def _update_env_file(key: str, default_val: str = "") -> None:
    """Append or update a key in .env and .env.example if missing."""
    for env_path in [Path.cwd() / ".env", Path.cwd() / ".env.example"]:
        if not env_path.exists():
            env_path.write_text(f"{key}={default_val}\n", encoding="utf-8")
            continue
        try:
            content = env_path.read_text(encoding="utf-8")
            if f"{key}=" not in content:
                content = content.rstrip() + f"\n{key}={default_val}\n"
                env_path.write_text(content, encoding="utf-8")
        except OSError:
            pass


def _add_to_settings(key: str) -> None:
    """Safely append missing setting field to config/settings.py."""
    candidates = [
        Path.cwd() / "config" / "settings.py",
        Path.cwd() / "core" / "config.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
            if key not in content:
                # Add to Settings class body before end
                content = content.rstrip() + f'\n    {key}: str = ""\n'
                candidate.write_text(content, encoding="utf-8")
            return


# ---------------------------------------------------------------------------
# kaira ai init
# ---------------------------------------------------------------------------


@app.command("init")
def ai_init(
    provider: Annotated[
        str,
        typer.Option(
            "--provider",
            "-p",
            help="Primary LLM provider: openai, anthropic, ollama, deepseek",
        ),
    ] = "openai",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing AI gateway")
    ] = False,
) -> None:
    """Initialize the AI Layer: scaffolds the LLM Gateway and sets up directories."""
    provider = provider.lower()
    valid_providers = {"openai", "anthropic", "ollama", "deepseek"}
    if provider not in valid_providers:
        console.print(
            f"[red]Error: Unsupported provider '{provider}'. Choose: {', '.join(sorted(valid_providers))}[/red]"
        )
        raise typer.Exit(1)

    env = _get_env_loader()
    cwd = Path.cwd()

    ai_dir = cwd / "services" / "ai"
    skills_dir = ai_dir / "skills"
    agents_dir = ai_dir / "agents"
    graphs_dir = ai_dir / "graphs"

    for d in (skills_dir, agents_dir, graphs_dir):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").touch(exist_ok=True)

    # Render Gateway
    gateway_content = env.get_template("ai_gateway.py.j2").render(
        primary_provider=provider
    )
    write_with_check(
        ai_dir / "gateway.py", gateway_content, force=force, non_interactive=True
    )

    # Setup Environment Variables
    env_keys = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ollama": "OLLAMA_HOST",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    key_to_add = env_keys[provider]
    default_val = (
        "http://localhost:11434" if provider == "ollama" else "your_api_key_here"
    )
    _update_env_file(key_to_add, default_val)
    _add_to_settings(key_to_add)

    console.print(
        Panel(
            f"[bold green]✨ AI Layer Initialized Successfully![/bold green]\n\n"
            f"• [cyan]Gateway:[/cyan] services/ai/gateway.py ({provider})\n"
            f"• [cyan]Skills Directory:[/cyan] services/ai/skills/\n"
            f"• [cyan]Agents Directory:[/cyan] services/ai/agents/\n"
            f"• [cyan]Graphs Directory:[/cyan] services/ai/graphs/\n"
            f"• [cyan]Config:[/cyan] Added {key_to_add} to settings and .env",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# kaira ai rag <Name>
# ---------------------------------------------------------------------------


@app.command("rag")
def ai_rag(
    name: Annotated[
        str,
        typer.Argument(
            help="Name of the RAG domain model (e.g. Document, Knowledge, Article)"
        ),
    ],
    vector_db: Annotated[
        str, typer.Option("--vector-db", help="Vector backend: pgvector or mongodb")
    ] = "pgvector",
    dim: Annotated[
        int, typer.Option("--dim", help="Embedding vector dimension size")
    ] = 1536,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite generated files")
    ] = False,
) -> None:
    """Scaffold a full 5-layer RAG pipeline (vector model, repository, ingestion service, streaming router)."""
    env = _get_env_loader()
    cwd = Path.cwd()

    model_name = _to_pascal(name)
    model_slug = _to_snake(name)
    table_name = f"{model_slug}_chunks"

    # Ensure directories exist
    for folder in ("models", "repositories", "services", "routers"):
        (cwd / folder).mkdir(parents=True, exist_ok=True)

    # Initialize AI gateway if not yet present
    gateway_path = cwd / "services" / "ai" / "gateway.py"
    if not gateway_path.exists():
        ai_init(provider="openai", force=False)

    ctx = {
        "model_name": model_name,
        "model_slug": model_slug,
        "table_name": table_name,
        "db_type": vector_db.lower(),
        "embedding_dim": dim,
    }

    # 1. Model
    model_content = env.get_template("ai_rag_model.py.j2").render(**ctx)
    write_with_check(
        cwd / "models" / f"{model_slug}.py",
        model_content,
        force=force,
        non_interactive=True,
    )

    # 2. Repository
    repo_content = env.get_template("ai_rag_repository.py.j2").render(**ctx)
    write_with_check(
        cwd / "repositories" / f"{model_slug}_repository.py",
        repo_content,
        force=force,
        non_interactive=True,
    )

    # 3. Service
    service_content = env.get_template("ai_rag_service.py.j2").render(**ctx)
    write_with_check(
        cwd / "services" / f"{model_slug}_service.py",
        service_content,
        force=force,
        non_interactive=True,
    )

    # 4. Router
    router_content = env.get_template("ai_rag_router.py.j2").render(**ctx)
    router_path = cwd / "routers" / f"{model_slug}_router.py"
    write_with_check(router_path, router_content, force=force, non_interactive=True)

    # 5. Wire into main.py safely
    main_path = cwd / "main.py"
    import_line = (
        f"from routers.{model_slug}_router import router as {model_slug}_router"
    )
    include_line = f"app.include_router({model_slug}_router)"
    register_router_in_main(main_path, import_line, include_line)

    console.print(
        Panel(
            f"[bold green]🚀 5-Layer RAG Pipeline Generated for '{model_name}'![/bold green]\n\n"
            f"• [cyan]Model:[/cyan] models/{model_slug}.py ({table_name})\n"
            f"• [cyan]Repository:[/cyan] repositories/{model_slug}_repository.py\n"
            f"• [cyan]Service:[/cyan] services/{model_slug}_service.py (Chunking & Embeddings)\n"
            f"• [cyan]Router:[/cyan] routers/{model_slug}_router.py (POST /ingest, POST /query SSE)\n"
            f"• [cyan]Wiring:[/cyan] Spliced into main.py",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# kaira ai skill <SkillName>
# ---------------------------------------------------------------------------


@app.command("skill")
def ai_skill(
    name: Annotated[
        str,
        typer.Argument(
            help="Name of the skill/tool to create (e.g. check_order, search_catalog)"
        ),
    ],
    from_service: Annotated[
        Optional[str],
        typer.Option(
            "--from-service",
            "-s",
            help="Existing Kaira service to wrap into this skill (e.g. OrderService)",
        ),
    ] = None,
    method: Annotated[
        Optional[str],
        typer.Option("--method", "-m", help="Specific method on the service to call"),
    ] = None,
    docstring: Annotated[
        Optional[str],
        typer.Option(
            "--docstring", "-d", help="Description of what the skill accomplishes"
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing skill file")
    ] = False,
) -> None:
    """Scaffold a reusable AI Agent Skill, optionally introspecting an existing Kaira service."""
    env = _get_env_loader()
    cwd = Path.cwd()
    skills_dir = cwd / "services" / "ai" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "__init__.py").touch(exist_ok=True)

    skill_slug = _to_snake(name)
    skill_class_name = _to_pascal(name)

    parameters = []
    service_name = None
    service_slug = None
    method_name = method

    if from_service:
        clean_service = from_service.replace("Service", "")
        service_name = f"{clean_service}Service"
        service_slug = f"{_to_snake(clean_service)}_service"
        service_file = cwd / "services" / f"{service_slug}.py"

        if service_file.exists():
            metas = introspect_service_file(service_file)
            target_class = next(
                (m for m in metas if m.class_name == service_name), None
            ) or (metas[0] if metas else None)
            if target_class and target_class.methods:
                chosen_method = next(
                    (m for m in target_class.methods if m.name == method),
                    target_class.methods[0],
                )
                method_name = chosen_method.name
                docstring = docstring or chosen_method.docstring
                parameters = chosen_method.parameters

    ctx = {
        "skill_name": name,
        "skill_slug": skill_slug,
        "skill_class_name": skill_class_name,
        "service_name": service_name,
        "service_slug": service_slug,
        "method_name": method_name,
        "docstring": docstring or f"Executes domain operation {name}.",
        "parameters": parameters,
    }

    content = env.get_template("ai_skill.py.j2").render(**ctx)
    target_file = skills_dir / f"{skill_slug}.py"
    write_with_check(target_file, content, force=force, non_interactive=True)

    console.print(
        Panel(
            f"[bold green]🧩 AI Skill Generated: '{name}'[/bold green]\n\n"
            f"• [cyan]File:[/cyan] services/ai/skills/{skill_slug}.py\n"
            f"• [cyan]Wrapped Service:[/cyan] {service_name or 'Custom Skill'}\n"
            f"• [cyan]Callable Method:[/cyan] {method_name or 'custom'}",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# kaira ai agent <AgentName>
# ---------------------------------------------------------------------------


@app.command("agent")
def ai_agent(
    name: Annotated[
        str,
        typer.Argument(help="Name of the agent (e.g. SupportBot, BillingAssistant)"),
    ],
    role: Annotated[
        str, typer.Option("--role", "-r", help="Agent role or domain focus")
    ] = "Helpful Assistant",
    skills: Annotated[
        Optional[str],
        typer.Option("--skills", "-s", help="Comma-separated skill names to bind"),
    ] = None,
    model: Annotated[
        str, typer.Option("--model", "-m", help="Target LLM model")
    ] = "gpt-4o",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing agent")
    ] = False,
) -> None:
    """Scaffold an autonomous Agent/Sub-Agent with prompt, bound skills, and streaming router."""
    env = _get_env_loader()
    cwd = Path.cwd()

    # Ensure AI init is present
    if not (cwd / "services" / "ai" / "gateway.py").exists():
        ai_init(provider="openai", force=False)

    agents_dir = cwd / "services" / "ai" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "__init__.py").touch(exist_ok=True)

    agent_slug = _to_snake(name)
    agent_class_name = _to_pascal(name)
    bound_skills = [s.strip() for s in skills.split(",")] if skills else []

    ctx = {
        "agent_name": name,
        "agent_slug": agent_slug,
        "agent_class_name": agent_class_name,
        "agent_role": role,
        "system_prompt": f"You are {name}, a specialized {role}.",
        "model_name": model,
        "bound_skills": bound_skills,
    }

    # 1. Agent Service
    agent_content = env.get_template("ai_agent.py.j2").render(**ctx)
    write_with_check(
        agents_dir / f"{agent_slug}.py",
        agent_content,
        force=force,
        non_interactive=True,
    )

    # 2. Agent Router
    router_ctx = {
        "is_supervisor": False,
        "agent_name": name,
        "agent_slug": agent_slug,
        "agent_class_name": agent_class_name,
    }
    router_content = env.get_template("ai_agent_router.py.j2").render(**router_ctx)
    router_path = cwd / "routers" / f"ai_{agent_slug}_router.py"
    write_with_check(router_path, router_content, force=force, non_interactive=True)

    # 3. Wire Router
    main_path = cwd / "main.py"
    import_line = (
        f"from routers.ai_{agent_slug}_router import router as ai_{agent_slug}_router"
    )
    include_line = f"app.include_router(ai_{agent_slug}_router)"
    register_router_in_main(main_path, import_line, include_line)

    console.print(
        Panel(
            f"[bold green]🤖 AI Agent Generated: '{name}'[/bold green]\n\n"
            f"• [cyan]Agent Class:[/cyan] services/ai/agents/{agent_slug}.py ({agent_class_name})\n"
            f"• [cyan]Role:[/cyan] {role}\n"
            f"• [cyan]Bound Skills:[/cyan] {', '.join(bound_skills) if bound_skills else 'None'}\n"
            f"• [cyan]Streaming Endpoint:[/cyan] POST /api/v1/ai/{agent_slug}/chat",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# kaira ai graph <GraphName>
# ---------------------------------------------------------------------------


@app.command("graph")
def ai_graph(
    name: Annotated[
        str,
        typer.Argument(
            help="Name of the multi-agent supervisor graph (e.g. SupportDesk)"
        ),
    ],
    subagents: Annotated[
        str,
        typer.Option(
            "--subagents",
            "-a",
            help="Comma-separated list of sub-agent names to register in this graph",
        ),
    ],
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing graph")
    ] = False,
) -> None:
    """Scaffold a Multi-Agent Supervisor workflow routing tasks across specialized sub-agents."""
    env = _get_env_loader()
    cwd = Path.cwd()

    graphs_dir = cwd / "services" / "ai" / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    (graphs_dir / "__init__.py").touch(exist_ok=True)

    graph_slug = _to_snake(name)
    supervisor_class_name = f"{_to_pascal(name)}Supervisor"

    subagent_list = []
    for sub in [s.strip() for s in subagents.split(",") if s.strip()]:
        # If the sub-agent doesn't exist yet, scaffold it!
        sub_slug = _to_snake(sub)
        sub_class = _to_pascal(sub)
        sub_file = cwd / "services" / "ai" / "agents" / f"{sub_slug}.py"
        if not sub_file.exists():
            ai_agent(name=sub, role=f"{sub} Specialist", skills=None, force=False)

        subagent_list.append(
            {
                "name": sub,
                "slug": sub_slug,
                "class_name": sub_class,
            }
        )

    ctx = {
        "supervisor_name": name,
        "supervisor_class_name": supervisor_class_name,
        "graph_slug": graph_slug,
        "subagents": subagent_list,
    }

    # 1. Graph Supervisor
    graph_content = env.get_template("ai_supervisor_graph.py.j2").render(**ctx)
    write_with_check(
        graphs_dir / f"{graph_slug}.py",
        graph_content,
        force=force,
        non_interactive=True,
    )

    # 2. Router for Supervisor
    router_ctx = {
        "is_supervisor": True,
        "supervisor_name": name,
        "supervisor_class_name": supervisor_class_name,
        "graph_slug": graph_slug,
    }
    router_content = env.get_template("ai_agent_router.py.j2").render(**router_ctx)
    router_path = cwd / "routers" / f"ai_{graph_slug}_router.py"
    write_with_check(router_path, router_content, force=force, non_interactive=True)

    # 3. Wire into main.py
    main_path = cwd / "main.py"
    import_line = (
        f"from routers.ai_{graph_slug}_router import router as ai_{graph_slug}_router"
    )
    include_line = f"app.include_router(ai_{graph_slug}_router)"
    register_router_in_main(main_path, import_line, include_line)

    console.print(
        Panel(
            f"[bold green]🌐 Multi-Agent Supervisor Graph Generated: '{name}'[/bold green]\n\n"
            f"• [cyan]Supervisor:[/cyan] services/ai/graphs/{graph_slug}.py ({supervisor_class_name})\n"
            f"• [cyan]Managed Sub-Agents:[/cyan] {', '.join([s['name'] for s in subagent_list])}\n"
            f"• [cyan]Endpoint:[/cyan] POST /api/v1/ai/{graph_slug}/chat (routes & streams dynamically)",
            border_style="green",
        )
    )
