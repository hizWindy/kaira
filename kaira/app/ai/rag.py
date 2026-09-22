"""RAG (Retrieval Augmented Generation) pipeline abstraction."""

from __future__ import annotations


class RAG:
    """Kaira RAG pipeline abstraction wrapping embeddings and vector stores."""

    def __init__(
        self,
        provider: str = "openai",
        vector_db: str = "pgvector",
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        self.provider = provider
        self.vector_db = vector_db
        self.embedding_model = embedding_model
        self._documents: list[str] = []

    async def ingest(self, documents: list[str]) -> int:
        """Ingest documents into the vector store."""
        self._documents.extend(documents)
        return len(documents)

    async def query(self, question: str, limit: int = 5) -> list[str]:
        """Query relevant documents for a question."""
        # Simple lexical match fallback if vector DB is not active
        results = [
            d
            for d in self._documents
            if any(word.lower() in d.lower() for word in question.split())
        ]
        return results[:limit]
