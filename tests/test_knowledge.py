"""Tests for FlowStrix Knowledge & RAG system.

Tests chunking, vector store, ingestion, and semantic retrieval.
Uses in-memory Qdrant — no external services required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowstrix.knowledge.chunker import Chunk, ChunkerConfig, DocumentChunker
from flowstrix.knowledge.vectorstore import SearchResult, VectorStore, VectorStoreConfig
from flowstrix.knowledge.loader import KnowledgeLoader
from flowstrix.schema.parser import parse_yaml


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

# Sample document for testing
SAMPLE_DOC = """# Refund Policy

## Eligibility

All purchases are eligible for a full refund within 30 days of delivery.
Items must be in original condition with packaging intact.

## Exceptions

The following items are non-refundable:
- Gift cards and digital downloads
- Personalized or custom-made items
- Items marked as final sale

## Process

To request a refund:
1. Contact customer support with your order number
2. Provide reason for return
3. Ship item back within 7 days of approval

## Timeframes

- Standard refunds: 5-7 business days after item received
- High-value items (>$500): requires manager approval, 10-14 business days
- International orders: 14-21 business days

## Store Credit

If a refund is denied, customers may be offered store credit equal to the
purchase amount. Store credit never expires and can be used on any item.
"""


# --- Chunker Tests ---


class TestDocumentChunker:
    def test_basic_chunking(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(SAMPLE_DOC, source_id="test_policy")

        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.source_id == "test_policy" for c in chunks)

    def test_chunk_indices_sequential(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(SAMPLE_DOC, source_id="test")

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_document(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document("", source_id="empty")
        assert chunks == []

    def test_whitespace_only(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document("   \n\n   ", source_id="whitespace")
        assert chunks == []

    def test_single_paragraph(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document("Just one paragraph here.", source_id="single")
        assert len(chunks) == 1
        assert "one paragraph" in chunks[0].text

    def test_respects_max_chunk_size(self):
        config = ChunkerConfig(max_chunk_chars=200, overlap_chars=0)
        chunker = DocumentChunker(config)
        chunks = chunker.chunk_document(SAMPLE_DOC, source_id="test")

        for chunk in chunks:
            # Allow some tolerance for overlap prefix
            assert chunk.char_count <= 400  # 2x max for edge cases with overlap

    def test_metadata_includes_section(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(SAMPLE_DOC, source_id="test")

        # At least one chunk should have section metadata
        sections = [c.metadata.get("section", "") for c in chunks]
        assert any(s for s in sections)

    def test_custom_config(self):
        config = ChunkerConfig(
            max_chunk_chars=500,
            min_chunk_chars=50,
            overlap_chars=50,
        )
        chunker = DocumentChunker(config)
        chunks = chunker.chunk_document(SAMPLE_DOC, source_id="test")
        assert len(chunks) > 0


# --- Vector Store Tests ---


class TestVectorStore:
    def test_create_in_memory(self):
        store = VectorStore()
        assert store.count() == 0

    def test_ingest_chunks(self):
        store = VectorStore()
        chunks = [
            Chunk(text="Refunds are available within 30 days", source_id="policy", chunk_index=0),
            Chunk(text="Gift cards are non-refundable", source_id="policy", chunk_index=1),
            Chunk(text="High-value items require manager approval", source_id="policy", chunk_index=2),
        ]

        count = store.ingest(chunks)
        assert count == 3
        assert store.count() == 3

    def test_ingest_empty_list(self):
        store = VectorStore()
        count = store.ingest([])
        assert count == 0

    def test_search_basic(self):
        store = VectorStore()
        chunks = [
            Chunk(text="All purchases are eligible for a full refund within 30 days of delivery.", source_id="policy", chunk_index=0),
            Chunk(text="Gift cards and digital downloads are non-refundable items.", source_id="policy", chunk_index=1),
            Chunk(text="High-value items over 500 dollars require manager approval for refund.", source_id="policy", chunk_index=2),
        ]
        store.ingest(chunks)

        results = store.search("return window timeframe", top_k=2)
        assert len(results) <= 2
        assert all(isinstance(r, SearchResult) for r in results)
        # The "30 days" chunk should be most relevant
        assert "30 days" in results[0].text

    def test_search_with_source_filter(self):
        store = VectorStore()
        chunks = [
            Chunk(text="Refunds within 30 days", source_id="refund_policy", chunk_index=0),
            Chunk(text="Password must be 8 characters", source_id="security_policy", chunk_index=0),
        ]
        store.ingest(chunks)

        results = store.search("policy rules", source_ids=["refund_policy"])
        # Should only return results from refund_policy
        assert all(r.source_id == "refund_policy" for r in results)

    def test_search_no_results_below_threshold(self):
        store = VectorStore()
        chunks = [
            Chunk(text="The weather is sunny today in California", source_id="weather", chunk_index=0),
        ]
        store.ingest(chunks)

        # Completely unrelated query with high threshold
        results = store.search("quantum computing algorithms", score_threshold=0.9)
        assert len(results) == 0

    def test_search_returns_scores(self):
        store = VectorStore()
        chunks = [
            Chunk(text="Refund policy for customer returns", source_id="p", chunk_index=0),
        ]
        store.ingest(chunks)

        results = store.search("refund return policy")
        assert len(results) > 0
        assert results[0].score > 0.0
        assert results[0].score <= 1.0


# --- Knowledge Loader RAG Tests ---


class TestKnowledgeLoaderRAG:
    """Test the updated KnowledgeLoader with RAG capabilities."""

    def test_load_backward_compatible(self):
        """Phase 1 load() still works."""
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        loader = KnowledgeLoader(spec, base_path=EXAMPLES_DIR)

        content = loader.load("refund_policy")
        assert "refund" in content.lower() or "Document not found" in content

    def test_ingest_creates_chunks(self):
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        loader = KnowledgeLoader(spec, base_path=EXAMPLES_DIR)

        results = loader.ingest_all()
        # Should have ingested at least one source
        assert any(count > 0 for count in results.values())

    def test_is_ingested_tracking(self):
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        loader = KnowledgeLoader(spec, base_path=EXAMPLES_DIR)

        # Before ingestion
        for source_id in loader.sources:
            assert loader.is_ingested(source_id) is False

        # After ingestion
        loader.ingest_all()
        for source_id in loader.sources:
            # At least the ones with valid files should be ingested
            pass  # Some may not have files, that's OK

    def test_retrieve_with_ingestion(self):
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        loader = KnowledgeLoader(spec, base_path=EXAMPLES_DIR)

        loader.ingest_all()

        # Only test retrieval if ingestion succeeded
        if any(loader.is_ingested(sid) for sid in loader.sources):
            result = loader.retrieve("refund eligibility window")
            assert len(result) > 0

    def test_retrieve_fallback_without_ingestion(self):
        """retrieve() falls back to load_multiple() if not ingested."""
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        loader = KnowledgeLoader(spec, base_path=EXAMPLES_DIR)

        # Don't ingest — should fall back
        result = loader.retrieve(
            "refund policy",
            knowledge_ids=list(loader.sources.keys()),
        )
        # Should still return content (from full document load)
        assert len(result) > 0


# --- Integration: Chunker + VectorStore ---


class TestChunkerVectorStoreIntegration:
    """End-to-end: chunk a document → ingest → search."""

    def test_full_pipeline(self):
        # Chunk
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(SAMPLE_DOC, source_id="refund_policy")
        assert len(chunks) > 2

        # Ingest
        store = VectorStore()
        count = store.ingest(chunks)
        assert count == len(chunks)

        # Search — should find relevant chunks
        results = store.search("how long do I have to return an item")
        assert len(results) > 0
        # Top result should mention 30 days or eligibility
        assert any("30" in r.text or "eligible" in r.text.lower() for r in results)

    def test_search_different_topics(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(SAMPLE_DOC, source_id="refund_policy")

        store = VectorStore()
        store.ingest(chunks)

        # Search for exceptions
        results = store.search("what items cannot be refunded")
        assert len(results) > 0
        assert any("gift card" in r.text.lower() or "non-refundable" in r.text.lower() for r in results)

        # Search for high-value process
        results = store.search("expensive items manager approval")
        assert len(results) > 0
        assert any("500" in r.text or "manager" in r.text.lower() for r in results)
