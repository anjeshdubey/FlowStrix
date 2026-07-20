"""
FlowStrix Document Chunker — splits documents into semantic chunks for RAG.

Chunking strategy: paragraph-based with overlap.
- Split on double newlines (markdown paragraphs)
- Merge small chunks to meet minimum size
- Add overlap between chunks for context continuity
- Preserve section headers for metadata
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chunk:
    """A single document chunk ready for embedding."""

    text: str
    source_id: str  # Knowledge source ID
    chunk_index: int
    metadata: dict = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass
class ChunkerConfig:
    """Configuration for document chunking."""

    max_chunk_chars: int = 800  # Max chars per chunk
    min_chunk_chars: int = 100  # Min chars (merge smaller chunks)
    overlap_chars: int = 100  # Overlap between consecutive chunks
    separator: str = "\n\n"  # Primary split point


class DocumentChunker:
    """Splits documents into overlapping semantic chunks.

    Strategy:
    1. Split on paragraph boundaries (double newline)
    2. Merge adjacent small paragraphs to meet min_chunk_chars
    3. Split oversized chunks by sentence boundaries
    4. Add overlap between consecutive chunks for continuity
    """

    def __init__(self, config: Optional[ChunkerConfig] = None):
        self.config = config or ChunkerConfig()

    def chunk_document(self, text: str, source_id: str) -> list[Chunk]:
        """Split a document into chunks.

        Args:
            text: Full document text.
            source_id: Knowledge source ID for metadata.

        Returns:
            List of Chunk objects ready for embedding.
        """
        if not text.strip():
            return []

        # Step 1: Split into paragraphs
        paragraphs = self._split_paragraphs(text)

        # Step 2: Merge small paragraphs
        merged = self._merge_small(paragraphs)

        # Step 3: Split oversized chunks
        sized = self._split_oversized(merged)

        # Step 4: Add overlap
        chunks_with_overlap = self._add_overlap(sized)

        # Step 5: Create Chunk objects with metadata
        chunks = []
        current_section = ""
        for i, chunk_text in enumerate(chunks_with_overlap):
            # Track section headers
            header_match = re.match(r"^(#{1,4})\s+(.+)", chunk_text.strip().split("\n")[0])
            if header_match:
                current_section = header_match.group(2)

            chunks.append(Chunk(
                text=chunk_text.strip(),
                source_id=source_id,
                chunk_index=i,
                metadata={
                    "section": current_section,
                    "char_count": len(chunk_text),
                },
            ))

        return chunks

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split text on paragraph boundaries."""
        parts = re.split(self.config.separator, text)
        return [p.strip() for p in parts if p.strip()]

    def _merge_small(self, paragraphs: list[str]) -> list[str]:
        """Merge consecutive small paragraphs."""
        if not paragraphs:
            return []

        merged = []
        current = paragraphs[0]

        for para in paragraphs[1:]:
            combined = current + "\n\n" + para
            if len(current) < self.config.min_chunk_chars and len(combined) <= self.config.max_chunk_chars:
                current = combined
            else:
                merged.append(current)
                current = para

        merged.append(current)
        return merged

    def _split_oversized(self, chunks: list[str]) -> list[str]:
        """Split chunks that exceed max_chunk_chars by sentence."""
        result = []
        for chunk in chunks:
            if len(chunk) <= self.config.max_chunk_chars:
                result.append(chunk)
            else:
                # Split by sentences
                sentences = re.split(r'(?<=[.!?])\s+', chunk)
                current = ""
                for sentence in sentences:
                    if current and len(current) + len(sentence) > self.config.max_chunk_chars:
                        result.append(current.strip())
                        current = sentence
                    else:
                        current = (current + " " + sentence).strip() if current else sentence
                if current:
                    result.append(current.strip())

        return result

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """Add overlap from previous chunk to current chunk."""
        if len(chunks) <= 1 or self.config.overlap_chars == 0:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            # Take last N chars from previous chunk as overlap prefix
            overlap = prev[-self.config.overlap_chars:] if len(prev) > self.config.overlap_chars else prev
            # Find a clean break point (word boundary)
            space_idx = overlap.find(" ")
            if space_idx > 0:
                overlap = overlap[space_idx + 1:]
            result.append(f"...{overlap}\n\n{chunks[i]}")

        return result
