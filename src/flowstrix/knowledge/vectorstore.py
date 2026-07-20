"""
FlowStrix Vector Store — Qdrant-backed semantic search for knowledge retrieval.

Wraps Qdrant with fastembed for local embeddings. Supports:
- In-memory mode (fast, no Docker needed — great for POC/testing)
- Persistent mode (local disk — survives restarts)
- Remote mode (Qdrant Cloud or Docker instance)

The embedding model (bge-small-en-v1.5) runs locally — no API calls needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from flowstrix.knowledge.chunker import Chunk


# --- Configuration ---

COLLECTION_NAME = "flowstrix_knowledge"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


@dataclass
class VectorStoreConfig:
    """Configuration for the vector store."""

    mode: str = "memory"  # "memory", "disk", "remote"
    path: Optional[str] = None  # For disk mode
    url: Optional[str] = None  # For remote mode
    api_key: Optional[str] = None  # For remote mode
    collection_name: str = COLLECTION_NAME


# --- Search Result ---

@dataclass
class SearchResult:
    """A single search result from the vector store."""

    text: str
    score: float
    source_id: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


# --- Vector Store ---

class VectorStore:
    """Qdrant-backed vector store with local embeddings.

    Usage:
        store = VectorStore()  # in-memory
        store.ingest(chunks)
        results = store.search("refund policy for electronics", top_k=3)
    """

    def __init__(self, config: Optional[VectorStoreConfig] = None):
        self.config = config or VectorStoreConfig()
        self._client = self._create_client()
        self._embedding_model = None  # Lazy-loaded
        self._ensure_collection()

    def _create_client(self) -> QdrantClient:
        """Create Qdrant client based on config mode."""
        if self.config.mode == "memory":
            return QdrantClient(":memory:")
        elif self.config.mode == "disk":
            path = self.config.path or "./.qdrant_data"
            return QdrantClient(path=path)
        elif self.config.mode == "remote":
            if not self.config.url:
                raise ValueError("Remote mode requires 'url' in config")
            return QdrantClient(
                url=self.config.url,
                api_key=self.config.api_key,
            )
        else:
            raise ValueError(f"Unknown mode: {self.config.mode}")

    def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        collections = self._client.get_collections().collections
        exists = any(c.name == self.config.collection_name for c in collections)

        if not exists:
            self._client.create_collection(
                collection_name=self.config.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )

    @property
    def embedding_model(self):
        """Lazy-load the embedding model (first call downloads ~30MB)."""
        if self._embedding_model is None:
            from fastembed import TextEmbedding
            self._embedding_model = TextEmbedding(EMBEDDING_MODEL)
        return self._embedding_model

    def ingest(self, chunks: list[Chunk]) -> int:
        """Ingest chunks into the vector store.

        Args:
            chunks: List of Chunk objects to embed and store.

        Returns:
            Number of chunks ingested.
        """
        if not chunks:
            return 0

        # Generate embeddings
        texts = [chunk.text for chunk in chunks]
        embeddings = list(self.embedding_model.embed(texts))

        # Create points
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            point_id = str(uuid.uuid4())
            points.append(PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload={
                    "text": chunk.text,
                    "source_id": chunk.source_id,
                    "chunk_index": chunk.chunk_index,
                    "metadata": chunk.metadata,
                },
            ))

        # Upsert into Qdrant
        self._client.upsert(
            collection_name=self.config.collection_name,
            points=points,
        )

        return len(points)

    def search(
        self,
        query: str,
        top_k: int = 3,
        source_ids: Optional[list[str]] = None,
        score_threshold: float = 0.3,
    ) -> list[SearchResult]:
        """Semantic search over ingested knowledge.

        Args:
            query: Natural language query.
            top_k: Number of results to return.
            source_ids: Filter to specific knowledge sources (optional).
            score_threshold: Minimum similarity score (0-1).

        Returns:
            List of SearchResult objects, sorted by relevance.
        """
        # Embed the query
        query_embedding = list(self.embedding_model.embed([query]))[0]

        # Build filter if source_ids specified
        search_filter = None
        if source_ids:
            # Filter to only chunks from specified sources
            search_filter = Filter(
                should=[
                    FieldCondition(key="source_id", match=MatchValue(value=sid))
                    for sid in source_ids
                ]
            )

        # Search using query_points API
        response = self._client.query_points(
            collection_name=self.config.collection_name,
            query=query_embedding.tolist(),
            limit=top_k,
            query_filter=search_filter,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                text=hit.payload["text"],
                score=hit.score,
                source_id=hit.payload["source_id"],
                chunk_index=hit.payload["chunk_index"],
                metadata=hit.payload.get("metadata", {}),
            )
            for hit in response.points
        ]

    def delete_source(self, source_id: str) -> None:
        """Delete all chunks for a given knowledge source."""
        self._client.delete(
            collection_name=self.config.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
            ),
        )

    def count(self, source_id: Optional[str] = None) -> int:
        """Count chunks in the store, optionally filtered by source."""
        if source_id is None:
            result = self._client.count(self.config.collection_name)
            return result.count

        # Count with filter via scroll
        results = self._client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
            ),
            with_payload=False,
            with_vectors=False,
        )
        # scroll returns (points, next_page_offset)
        return len(results[0])
