"""
FlowStrix Knowledge Loader — File-based + vector-based knowledge retrieval.

Two modes:
- Phase 1 (fallback): Direct file reading, full document injection
- Phase 3 (RAG): Semantic chunking + vector search, returns relevant snippets

The loader auto-detects which mode to use based on whether the vector store
has been populated for the requested knowledge sources.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from flowstrix.schema.models import AgentSpec, KnowledgeSource, KnowledgeSourceType

logger = logging.getLogger(__name__)


class KnowledgeLoader:
    """Loads knowledge content for injection into reasoning steps.

    Supports two retrieval modes:
    - `load()` / `load_multiple()` — full document (Phase 1, backward-compatible)
    - `retrieve()` — semantic search (Phase 3, requires ingestion first)

    Usage:
        loader = KnowledgeLoader(spec, base_path=Path("./examples"))

        # Phase 1: full document injection
        content = loader.load("refund_policy")

        # Phase 3: semantic retrieval (after ingestion)
        loader.ingest_all()
        snippets = loader.retrieve("30-day return window", knowledge_ids=["refund_policy"])
    """

    def __init__(self, spec: AgentSpec, base_path: Optional[Path] = None):
        """Initialize with agent spec and optional base path for resolving relative URIs.

        Args:
            spec: Agent specification containing knowledge source definitions.
            base_path: Directory to resolve relative file paths against.
                       Defaults to current working directory.
        """
        self.sources = {ks.id: ks for ks in spec.knowledge}
        self.base_path = base_path or Path.cwd()
        self._cache: dict[str, str] = {}
        self._vector_store = None
        self._ingested_sources: set[str] = set()

    @property
    def vector_store(self):
        """Lazy-create vector store on first RAG access."""
        if self._vector_store is None:
            from flowstrix.knowledge.vectorstore import VectorStore
            self._vector_store = VectorStore()
        return self._vector_store

    def load(self, knowledge_id: str) -> str:
        """Load full knowledge content by ID (Phase 1 mode).

        Returns the full document content. For large documents,
        prefer `retrieve()` with a query for targeted snippets.
        """
        if knowledge_id in self._cache:
            return self._cache[knowledge_id]

        if knowledge_id not in self.sources:
            return f"[Knowledge source '{knowledge_id}' not found]"

        source = self.sources[knowledge_id]
        content = self._load_source(source)
        self._cache[knowledge_id] = content
        return content

    def load_multiple(self, knowledge_ids: list[str]) -> str:
        """Load and concatenate multiple knowledge sources (Phase 1 mode)."""
        parts = []
        for kid in knowledge_ids:
            content = self.load(kid)
            source = self.sources.get(kid)
            label = source.description if source else kid
            parts.append(f"### {label}\n\n{content}")
        return "\n\n---\n\n".join(parts)

    # --- Phase 3: RAG Methods ---

    def ingest(self, knowledge_id: str) -> int:
        """Ingest a single knowledge source into the vector store.

        Returns the number of chunks created.
        """
        if knowledge_id not in self.sources:
            logger.warning(f"Knowledge source '{knowledge_id}' not found in spec")
            return 0

        source = self.sources[knowledge_id]
        content = self._load_raw_content(source)
        if not content or content.startswith("["):
            logger.warning(f"Could not load content for '{knowledge_id}'")
            return 0

        from flowstrix.knowledge.chunker import DocumentChunker
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(content, source_id=knowledge_id)

        if not chunks:
            return 0

        count = self.vector_store.ingest(chunks)
        self._ingested_sources.add(knowledge_id)
        logger.info(f"Ingested '{knowledge_id}': {count} chunks")
        return count

    def ingest_all(self) -> dict[str, int]:
        """Ingest all knowledge sources into the vector store.

        Returns a dict of {source_id: chunk_count}.
        """
        results = {}
        for source_id in self.sources:
            count = self.ingest(source_id)
            results[source_id] = count
        return results

    def retrieve(
        self,
        query: str,
        knowledge_ids: Optional[list[str]] = None,
        top_k: int = 3,
        score_threshold: float = 0.3,
    ) -> str:
        """Retrieve relevant knowledge snippets via semantic search.

        If the requested sources haven't been ingested yet, falls back to
        full document loading (Phase 1 behavior) with a warning.

        Args:
            query: Natural language query (usually the reason step's prompt context).
            knowledge_ids: Filter to specific sources. None = search all.
            top_k: Max number of chunks to return.
            score_threshold: Minimum similarity score (0-1).

        Returns:
            Formatted string of relevant knowledge snippets.
        """
        # Check if any requested sources are ingested
        ids_to_search = knowledge_ids or list(self.sources.keys())
        ingested_ids = [sid for sid in ids_to_search if sid in self._ingested_sources]

        if not ingested_ids:
            # Fallback to Phase 1: full document loading
            logger.debug("No ingested sources found, falling back to full document load")
            if knowledge_ids:
                return self.load_multiple(knowledge_ids)
            return self.load_multiple(list(self.sources.keys()))

        # Semantic search
        results = self.vector_store.search(
            query=query,
            top_k=top_k,
            source_ids=ingested_ids,
            score_threshold=score_threshold,
        )

        if not results:
            # No good matches — fall back to full load
            logger.debug(f"No semantic matches for query, falling back to full load")
            return self.load_multiple(ids_to_search)

        # Format results
        parts = []
        for i, result in enumerate(results, 1):
            source = self.sources.get(result.source_id)
            source_label = source.description if source else result.source_id
            section = result.metadata.get("section", "")
            header = f"[{source_label}]"
            if section:
                header += f" > {section}"

            parts.append(f"**{header}** (relevance: {result.score:.0%})\n{result.text}")

        return "\n\n---\n\n".join(parts)

    def is_ingested(self, knowledge_id: str) -> bool:
        """Check if a knowledge source has been ingested into the vector store."""
        return knowledge_id in self._ingested_sources

    # --- Internal Methods ---

    def _load_source(self, source: KnowledgeSource) -> str:
        """Load content from a knowledge source based on its type."""
        content = self._load_raw_content(source)
        # Truncate for Phase 1 direct injection (RAG doesn't need this)
        max_chars = 4000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... truncated — use RAG mode for full retrieval]"
        return content

    def _load_raw_content(self, source: KnowledgeSource) -> str:
        """Load raw content without truncation (used by RAG ingestion)."""
        if source.source_type == KnowledgeSourceType.DOCUMENT:
            return self._load_document(source.uri)
        elif source.source_type == KnowledgeSourceType.URL:
            return f"[URL source '{source.uri}' — web fetching not yet implemented]"
        elif source.source_type == KnowledgeSourceType.API:
            return f"[API source '{source.uri}' — API fetching not yet implemented]"
        elif source.source_type == KnowledgeSourceType.DATABASE:
            return f"[Database source '{source.uri}' — DB queries not yet implemented]"
        else:
            return f"[Unknown source type: {source.source_type}]"

    def _load_document(self, uri: str) -> str:
        """Load a document file from disk."""
        path = Path(uri)
        if not path.is_absolute():
            path = self.base_path / path

        if not path.exists():
            return f"[Document not found: {path}]"

        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            return f"[Error reading {path}: {e}]"
