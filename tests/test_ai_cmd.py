"""CLI and integration tests for Kaira AI, RAG, and Multi-Agent / Skills commands."""

from __future__ import annotations

from pathlib import Path
from click.testing import CliRunner
from typer.main import get_command

from kaira.main import app
from kaira.core.ai_introspect import introspect_service_file, introspect_all_services

runner = CliRunner()
cli = get_command(app)


def run(*args: str):
    """Invoke the kaira CLI with given arguments."""
    return runner.invoke(cli, list(args))


class TestAiCommandGroup:
    def test_ai_help(self):
        result = run("ai", "--help")
        assert result.exit_code == 0
        assert "init" in result.output
        assert "rag" in result.output
        assert "skill" in result.output
        assert "agent" in result.output
        assert "graph" in result.output

    def test_ai_init_scaffolds_gateway_and_dirs(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            (cwd / "config").mkdir(parents=True, exist_ok=True)
            (cwd / "config" / "settings.py").write_text("class Settings:\n    app_name: str = 'TestApp'\n", encoding="utf-8")

            result = run("ai", "init", "--provider", "openai")
            assert result.exit_code == 0
            assert "AI Layer Initialized" in result.output

            gateway_file = cwd / "services" / "ai" / "gateway.py"
            assert gateway_file.is_file()
            content = gateway_file.read_text(encoding="utf-8")
            assert "class LLMGateway" in content
            assert "primary_provider: str = \"openai\"" in content

            # Directories
            assert (cwd / "services" / "ai" / "skills").is_dir()
            assert (cwd / "services" / "ai" / "agents").is_dir()
            assert (cwd / "services" / "ai" / "graphs").is_dir()

            # Config update
            env_content = (cwd / ".env").read_text(encoding="utf-8")
            assert "OPENAI_API_KEY=" in env_content
            settings_content = (cwd / "config" / "settings.py").read_text(encoding="utf-8")
            assert "OPENAI_API_KEY" in settings_content

    def test_ai_rag_scaffolds_5_layer_pipeline(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            (cwd / "main.py").write_text(
                "from fastapi import FastAPI\napp = FastAPI()\n# [ROUTER_REGISTRATION]\n",
                encoding="utf-8",
            )

            result = run("ai", "rag", "KnowledgeDoc", "--vector-db", "pgvector")
            assert result.exit_code == 0
            assert "5-Layer RAG Pipeline Generated" in result.output

            # 1. Model
            model_file = cwd / "models" / "knowledge_doc.py"
            assert model_file.is_file()
            assert "class KnowledgeDocChunk" in model_file.read_text(encoding="utf-8")

            # 2. Repository
            repo_file = cwd / "repositories" / "knowledge_doc_repository.py"
            assert repo_file.is_file()
            assert "similarity_search" in repo_file.read_text(encoding="utf-8")

            # 3. Service
            service_file = cwd / "services" / "knowledge_doc_service.py"
            assert service_file.is_file()
            service_text = service_file.read_text(encoding="utf-8")
            assert "ingest_document" in service_text
            assert "answer_query_stream" in service_text

            # 4. Router
            router_file = cwd / "routers" / "knowledge_doc_router.py"
            assert router_file.is_file()
            router_text = router_file.read_text(encoding="utf-8")
            assert "/api/v1/knowledge_doc" in router_text
            assert "StreamingResponse" in router_text

            # 5. Spliced into main.py
            main_text = (cwd / "main.py").read_text(encoding="utf-8")
            assert "knowledge_doc_router" in main_text

    def test_ai_skill_creation_and_introspection(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            services_dir = cwd / "services"
            services_dir.mkdir(parents=True, exist_ok=True)
            
            # Create a sample OrderService to introspect
            order_service_code = (
                "class OrderService:\n"
                "    @staticmethod\n"
                "    async def cancel_order(order_id: int, reason: str) -> bool:\n"
                "        '''Cancel an active order given its ID and reason.'''\n"
                "        return True\n"
            )
            (services_dir / "order_service.py").write_text(order_service_code, encoding="utf-8")

            # Test AST Introspection directly
            metas = introspect_service_file(services_dir / "order_service.py")
            assert len(metas) == 1
            assert metas[0].class_name == "OrderService"
            assert len(metas[0].methods) == 1
            assert metas[0].methods[0].name == "cancel_order"
            assert metas[0].methods[0].docstring == "Cancel an active order given its ID and reason."

            # Run CLI to create skill from service
            result = run("ai", "skill", "cancel_order", "--from-service", "OrderService")
            assert result.exit_code == 0
            assert "AI Skill Generated" in result.output

            skill_file = cwd / "services" / "ai" / "skills" / "cancel_order.py"
            assert skill_file.is_file()
            skill_text = skill_file.read_text(encoding="utf-8")
            assert "OrderService.cancel_order" in skill_text
            assert "order_id" in skill_text
            assert "reason" in skill_text

    def test_ai_agent_scaffolding(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            (cwd / "main.py").write_text("app = FastAPI()\n# [ROUTER_REGISTRATION]\n", encoding="utf-8")

            result = run(
                "ai", "agent", "SupportBot",
                "--role", "Customer Care Specialist",
                "--skills", "refund_skill,lookup_skill",
            )
            assert result.exit_code == 0
            assert "AI Agent Generated: 'SupportBot'" in result.output

            agent_file = cwd / "services" / "ai" / "agents" / "support_bot.py"
            assert agent_file.is_file()
            agent_text = agent_file.read_text(encoding="utf-8")
            assert "class SupportBot" in agent_text
            assert "Customer Care Specialist" in agent_text

            router_file = cwd / "routers" / "ai_support_bot_router.py"
            assert router_file.is_file()
            assert "StreamingResponse" in router_file.read_text(encoding="utf-8")

    def test_ai_graph_supervisor_scaffolding(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            (cwd / "main.py").write_text("app = FastAPI()\n# [ROUTER_REGISTRATION]\n", encoding="utf-8")

            result = run("ai", "graph", "OmniDesk", "--subagents", "BillingBot,TechBot")
            assert result.exit_code == 0
            assert "Multi-Agent Supervisor Graph Generated" in result.output

            graph_file = cwd / "services" / "ai" / "graphs" / "omni_desk.py"
            assert graph_file.is_file()
            graph_text = graph_file.read_text(encoding="utf-8")
            assert "class OmniDeskSupervisor" in graph_text
            assert "BillingBot" in graph_text
            assert "TechBot" in graph_text

            # Automatically generated sub-agents
            assert (cwd / "services" / "ai" / "agents" / "billing_bot.py").is_file()
            assert (cwd / "services" / "ai" / "agents" / "tech_bot.py").is_file()

            # Supervisor router
            assert (cwd / "routers" / "ai_omni_desk_router.py").is_file()

    def test_ai_non_destructive_brownfield(self, tmp_path):
        """Ensure existing project files are preserved when adding AI capabilities."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            (cwd / "models").mkdir(parents=True, exist_ok=True)
            user_model = cwd / "models" / "user.py"
            user_model.write_text("class User:\n    id: int\n", encoding="utf-8")

            (cwd / "main.py").write_text(
                "# Existing FastAPI app\nfrom fastapi import FastAPI\napp = FastAPI()\n# [ROUTER_REGISTRATION]\n",
                encoding="utf-8",
            )

            # Augment with RAG
            result = run("ai", "rag", "KnowledgeDoc")
            assert result.exit_code == 0

            # Existing files remain untouched
            assert user_model.read_text(encoding="utf-8") == "class User:\n    id: int\n"
            main_text = (cwd / "main.py").read_text(encoding="utf-8")
            assert "# Existing FastAPI app" in main_text
            assert "knowledge_doc_router" in main_text
