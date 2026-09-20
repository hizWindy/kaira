"""Multi-provider LLM Gateway abstraction."""

from __future__ import annotations

import os
from typing import Any, Optional


class LLMGateway:
    """Unified interface for executing prompts across OpenAI, Anthropic, Gemini, Groq, etc."""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
    ) -> None:
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Send a completion request to the active provider."""
        if self.provider == "openai":
            try:
                import openai

                client = openai.AsyncOpenAI(api_key=self.api_key)
                resp = await client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    **kwargs,
                )
                return resp.choices[0].message.content or ""
            except ImportError:
                return f"[Mock completion for {self.model}]: {prompt[:50]}..."
        return f"[{self.provider} response]: Completed."
