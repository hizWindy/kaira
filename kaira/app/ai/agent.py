"""AI Agent abstraction layer wrapping LangChain / LangGraph."""

from __future__ import annotations

from typing import Any


class Agent:
    """Kaira AI Agent abstraction."""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o",
        tools: list[Any] | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.tools = tools or []

    async def run(self, query: str) -> str:
        """Run the agent on a user query."""
        try:
            import langchain_openai  # noqa: F401

            return f"Agent response for '{query}' using {self.model}"
        except ImportError:
            return f"Agent (fallback) executed '{query}' on {self.model}"
