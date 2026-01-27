"""Vector memory for semantic search with efficient similarity search.

This module provides a production-ready vector memory implementation with:
- Support for multiple embedding backends (sentence-transformers, OpenAI, custom)
- Efficient similarity search using cosine similarity with optional FAISS indexing
- Batch operations for performance
- Metadata filtering and hybrid search
- Persistence support
"""

import math
import pickle
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from routekitai.core.errors import RuntimeError as RouteKitRuntimeError


class VectorMemoryError(RouteKitRuntimeError):
    """Error raised by vector memory operations."""

    pass


class EmbeddingBackend:
    """Abstract embedding backend interface."""

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector as list of floats
        """
        raise NotImplementedError

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (optional optimization).

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        return [self.embed(text) for text in texts]

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        raise NotImplementedError


class SimpleEmbeddingBackend(EmbeddingBackend):
    """Simple TF-IDF-like embedding backend for MVP (no external dependencies).

    Uses character-level n-grams and frequency-based weighting.
    For production, use SentenceTransformerBackend or OpenAIBackend.
    """

    def __init__(self, dimension: int = 384, ngram_size: int = 3) -> None:
        """Initialize simple embedding backend.

        Args:
            dimension: Embedding dimension
            ngram_size: N-gram size for character-level features
        """
        self._dimension = dimension
        self.ngram_size = ngram_size
        self._vocab: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._document_count = 0
        self._document_ngrams: list[set[str]] = []

    def _extract_ngrams(self, text: str) -> list[str]:
        """Extract character n-grams from text."""
        text_lower = text.lower()
        ngrams = []
        for i in range(len(text_lower) - self.ngram_size + 1):
            ngram = text_lower[i : i + self.ngram_size]
            ngrams.append(ngram)
        return ngrams

    def _build_vocab(self, texts: list[str]) -> None:
        """Build vocabulary from texts."""
        ngram_counts: dict[str, int] = defaultdict(int)
        for text in texts:
            ngrams = set(self._extract_ngrams(text))
            self._document_ngrams.append(ngrams)
            for ngram in ngrams:
                ngram_counts[ngram] += 1

        # Build vocab with most frequent n-grams
        sorted_ngrams = sorted(ngram_counts.items(), key=lambda x: x[1], reverse=True)
        self._vocab = {
            ngram: idx for idx, (ngram, _) in enumerate(sorted_ngrams[: self._dimension])
        }

        # Calculate IDF
        self._document_count = len(texts)
        for ngram in self._vocab.keys():
            doc_freq = sum(1 for doc_ngrams in self._document_ngrams if ngram in doc_ngrams)
            self._idf[ngram] = (
                math.log((self._document_count + 1) / (doc_freq + 1)) if doc_freq > 0 else 0.0
            )

    def embed(self, text: str) -> list[float]:
        """Generate embedding using TF-IDF on character n-grams."""
        if not self._vocab:
            # Initialize with empty vocab if not trained
            return [0.0] * self._dimension

        ngrams = self._extract_ngrams(text)
        ngram_counts: dict[str, int] = defaultdict(int)
        for ngram in ngrams:
            if ngram in self._vocab:
                ngram_counts[ngram] += 1

        # Build TF-IDF vector
        vector = [0.0] * self._dimension
        total_ngrams = len(ngrams) if ngrams else 1

        for ngram, count in ngram_counts.items():
            if ngram in self._vocab:
                idx = self._vocab[ngram]
                tf = count / total_ngrams
                idf = self._idf.get(ngram, 0.0)
                vector[idx] = tf * idf

        # L2 normalization (important for cosine similarity)
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        else:
            # If all zeros, return a small uniform vector to avoid division issues
            vector = [1.0 / math.sqrt(self._dimension)] * self._dimension

        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for batch with vocabulary building."""
        if not self._vocab and texts:
            # Build vocab from batch
            self._build_vocab(texts)

        return [self.embed(text) for text in texts]

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension


class VectorMemory(BaseModel):
    """Production-ready vector memory with efficient similarity search.

    Features:
    - Multiple embedding backends (simple, sentence-transformers, OpenAI)
    - Efficient cosine similarity search
    - Optional FAISS indexing for large-scale search
    - Metadata filtering
    - Batch operations
    - Persistence support
    """

    dimension: int = Field(default=384, description="Vector dimension")
    backend: str = Field(
        default="simple", description="Embedding backend (simple, sentence-transformers, openai)"
    )
    use_faiss: bool = Field(default=False, description="Use FAISS for large-scale indexing")
    persist_path: Path | None = Field(default=None, description="Path to persist vectors")
    similarity_threshold: float = Field(
        default=0.0, description="Minimum similarity threshold for search"
    )

    def __init__(self, **data: Any) -> None:
        """Initialize vector memory."""
        super().__init__(**data)
        self._vectors: dict[str, dict[str, Any]] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._embedding_backend: EmbeddingBackend | None = None
        self._faiss_index: Any = None  # FAISS index if available
        self._id_to_vector_id: dict[int, str] = {}  # Map FAISS index to vector ID

    def _get_embedding_backend(self) -> EmbeddingBackend:
        """Get or create embedding backend."""
        if self._embedding_backend is None:
            if self.backend == "simple":
                self._embedding_backend = SimpleEmbeddingBackend(dimension=self.dimension)
            elif self.backend == "sentence-transformers":
                try:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer("all-MiniLM-L6-v2")
                    self._embedding_backend = SentenceTransformerBackend(model)
                except ImportError:
                    raise VectorMemoryError(
                        "sentence-transformers not installed. Install with: pip install sentence-transformers",
                        context={"backend": self.backend},
                    ) from None
            elif self.backend == "openai":
                try:
                    import os

                    api_key = os.getenv("OPENAI_API_KEY")
                    if not api_key:
                        raise VectorMemoryError(
                            "OPENAI_API_KEY environment variable not set",
                            context={"backend": self.backend},
                        )
                    self._embedding_backend = OpenAIBackend(
                        api_key=api_key, dimension=self.dimension
                    )
                except ImportError:
                    raise VectorMemoryError(
                        "openai package not installed. Install with: pip install openai",
                        context={"backend": self.backend},
                    ) from None
            else:
                raise VectorMemoryError(
                    f"Unknown embedding backend: {self.backend}",
                    context={
                        "backend": self.backend,
                        "available": ["simple", "sentence-transformers", "openai"],
                    },
                )
        return self._embedding_backend

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score between -1 and 1
        """
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=True))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(a * a for a in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _initialize_faiss(self) -> None:
        """Initialize FAISS index if available and enabled."""
        if not self.use_faiss:
            return

        try:
            import faiss  # noqa: F401
            import numpy as np  # noqa: F401
        except ImportError as e:
            # FAISS or numpy not available, fall back to linear search
            self.use_faiss = False
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"FAISS not available ({e}). Falling back to linear search. "
                "Install with: pip install faiss-cpu numpy"
            )
            return

        # Use L2 distance index (we'll convert to cosine similarity)
        self._faiss_index = faiss.IndexFlatL2(self.dimension)

    async def add(self, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Add text to vector memory with automatic embedding.

        Args:
            text: Text to embed and store
            metadata: Optional metadata dictionary

        Returns:
            ID of stored vector
        """
        if not text.strip():
            raise VectorMemoryError("Cannot add empty text to vector memory")

        vector_id = str(uuid.uuid4())
        backend = self._get_embedding_backend()

        # For simple backend, rebuild vocab with all texts (existing + new)
        if isinstance(backend, SimpleEmbeddingBackend):
            existing_texts = [v["text"] for v in self._vectors.values()]
            all_texts = existing_texts + [text]
            backend._build_vocab(all_texts)

        # Generate embedding
        embedding = backend.embed(text)

        # Store vector data
        self._vectors[vector_id] = {
            "text": text,
            "metadata": metadata or {},
            "id": vector_id,
            "embedding_dim": len(embedding),
        }

        # Store embedding
        self._embeddings[vector_id] = embedding

        # Add to FAISS index if enabled
        if self.use_faiss:
            if self._faiss_index is None:
                self._initialize_faiss()

            if self._faiss_index is not None:
                try:
                    import faiss  # noqa: F401
                    import numpy as np
                except ImportError as e:
                    raise VectorMemoryError(
                        f"FAISS dependencies not available: {e}. Install with: pip install faiss-cpu numpy",
                        context={"operation": "add", "use_faiss": True},
                    ) from e

                embedding_array = np.array([embedding], dtype=np.float32)
                idx = self._faiss_index.ntotal
                self._faiss_index.add(embedding_array)
                self._id_to_vector_id[idx] = vector_id

        return vector_id

    async def add_batch(
        self, texts: list[str], metadata_list: list[dict[str, Any]] | None = None
    ) -> list[str]:
        """Add multiple texts to vector memory efficiently.

        Args:
            texts: List of texts to embed and store
            metadata_list: Optional list of metadata dictionaries

        Returns:
            List of vector IDs
        """
        if not texts:
            return []

        if metadata_list and len(metadata_list) != len(texts):
            raise VectorMemoryError("metadata_list length must match texts length")

        backend = self._get_embedding_backend()

        # For simple backend, rebuild vocab with all texts
        if isinstance(backend, SimpleEmbeddingBackend):
            existing_texts = [v["text"] for v in self._vectors.values()]
            all_texts = existing_texts + texts
            backend._build_vocab(all_texts)

        # Batch embed
        embeddings = backend.embed_batch(texts)

        vector_ids = []
        for idx, (text, embedding) in enumerate(zip(texts, embeddings, strict=True)):
            vector_id = str(uuid.uuid4())
            metadata = metadata_list[idx] if metadata_list else None

            self._vectors[vector_id] = {
                "text": text,
                "metadata": metadata or {},
                "id": vector_id,
                "embedding_dim": len(embedding),
            }
            self._embeddings[vector_id] = embedding
            vector_ids.append(vector_id)

        # Batch add to FAISS if enabled
        if self.use_faiss and embeddings:
            if self._faiss_index is None:
                self._initialize_faiss()

            if self._faiss_index is not None:
                try:
                    import faiss  # noqa: F401
                    import numpy as np
                except ImportError as e:
                    raise VectorMemoryError(
                        f"FAISS dependencies not available: {e}. Install with: pip install faiss-cpu numpy",
                        context={"operation": "add_batch", "use_faiss": True},
                    ) from e

                embedding_array = np.array(embeddings, dtype=np.float32)
                start_idx = self._faiss_index.ntotal
                self._faiss_index.add(embedding_array)

                for i, vector_id in enumerate(vector_ids):
                    self._id_to_vector_id[start_idx + i] = vector_id

        return vector_ids

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors using efficient similarity search.

        Args:
            query: Search query text
            top_k: Number of results to return
            filter_metadata: Optional metadata filter (exact match on keys)
            min_similarity: Minimum similarity threshold (overrides instance default)

        Returns:
            List of similar vectors with metadata, scores, and distances
        """
        if not query.strip():
            return []

        if not self._vectors:
            return []

        backend = self._get_embedding_backend()

        # For simple backend, ensure vocab is built from existing vectors
        if isinstance(backend, SimpleEmbeddingBackend) and not backend._vocab:
            existing_texts = [v["text"] for v in self._vectors.values()]
            if existing_texts:
                backend._build_vocab(existing_texts)
            else:
                # No vectors yet, return empty
                return []

        query_embedding = backend.embed(query)

        threshold = min_similarity if min_similarity is not None else self.similarity_threshold

        results = []

        if self.use_faiss and self._faiss_index is not None:
            # Use FAISS for efficient search
            try:
                import faiss  # noqa: F401
                import numpy as np
            except ImportError as e:
                raise VectorMemoryError(
                    f"FAISS dependencies not available: {e}. Install with: pip install faiss-cpu numpy",
                    context={"operation": "search", "use_faiss": True},
                ) from e

            query_array = np.array([query_embedding], dtype=np.float32)
            k = min(top_k * 2, self._faiss_index.ntotal)  # Get more candidates for filtering

            if k > 0:
                distances, indices = self._faiss_index.search(query_array, k)

                for dist, idx in zip(distances[0], indices[0], strict=True):
                    vector_id = self._id_to_vector_id.get(idx)
                    if vector_id is None:
                        continue

                    vector_data = self._vectors[vector_id]
                    vector_embedding = self._embeddings[vector_id]

                    # Convert L2 distance to cosine similarity
                    # L2_dist^2 = 2 * (1 - cos_sim)
                    # cos_sim = 1 - (L2_dist^2 / 2)
                    similarity = 1.0 - (dist * dist / 2.0)

                    if similarity >= threshold:
                        # Apply metadata filter
                        if filter_metadata:
                            if not all(
                                vector_data.get("metadata", {}).get(k) == v
                                for k, v in filter_metadata.items()
                            ):
                                continue

                        results.append(
                            {
                                "id": vector_id,
                                "text": vector_data["text"],
                                "metadata": vector_data["metadata"],
                                "score": similarity,
                                "distance": dist,
                            }
                        )
        else:
            # Linear search with cosine similarity
            for vector_id, vector_data in self._vectors.items():
                vector_embedding = self._embeddings[vector_id]

                # Apply metadata filter first (early exit)
                if filter_metadata:
                    if not all(
                        vector_data.get("metadata", {}).get(k) == v
                        for k, v in filter_metadata.items()
                    ):
                        continue

                # Calculate cosine similarity
                similarity = self._cosine_similarity(query_embedding, vector_embedding)

                if similarity >= threshold:
                    results.append(
                        {
                            "id": vector_id,
                            "text": vector_data["text"],
                            "metadata": vector_data["metadata"],
                            "score": similarity,
                            "distance": 1.0 - similarity,  # Convert similarity to distance
                        }
                    )

        # Sort by score descending and return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete(self, vector_id: str) -> bool:
        """Delete a vector from memory.

        Args:
            vector_id: ID of vector to delete

        Returns:
            True if deleted, False if not found
        """
        if vector_id not in self._vectors:
            return False

        del self._vectors[vector_id]
        del self._embeddings[vector_id]

        # Note: FAISS doesn't support deletion efficiently, so we'd need to rebuild
        # For now, we'll just mark it as needing rebuild
        if self.use_faiss:
            # In production, you'd want to rebuild the index periodically
            pass

        return True

    async def get(self, vector_id: str) -> dict[str, Any] | None:
        """Get vector data by ID.

        Args:
            vector_id: Vector ID

        Returns:
            Vector data or None if not found
        """
        return self._vectors.get(vector_id)

    def save(self, path: Path | str) -> None:
        """Save vector memory to disk.

        Args:
            path: Path to save to
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "vectors": self._vectors,
            "embeddings": self._embeddings,
            "dimension": self.dimension,
            "backend": self.backend,
            "id_to_vector_id": self._id_to_vector_id,
        }

        with open(path, "wb") as f:
            pickle.dump(data, f)

    @classmethod
    def load(cls, path: Path | str, **kwargs: Any) -> "VectorMemory":
        """Load vector memory from disk.

        Args:
            path: Path to load from
            **kwargs: Additional initialization parameters

        Returns:
            Loaded VectorMemory instance
        """
        path = Path(path)
        if not path.exists():
            raise VectorMemoryError(f"Vector memory file not found: {path}")

        with open(path, "rb") as f:
            data = pickle.load(f)

        instance = cls(
            dimension=data.get("dimension", 384), backend=data.get("backend", "simple"), **kwargs
        )

        instance._vectors = data.get("vectors", {})
        instance._embeddings = data.get("embeddings", {})
        instance._id_to_vector_id = data.get("id_to_vector_id", {})

        # Rebuild vocabulary for SimpleEmbeddingBackend if needed
        if instance.backend == "simple" and instance._vectors:
            backend = instance._get_embedding_backend()
            if isinstance(backend, SimpleEmbeddingBackend):
                existing_texts = [v["text"] for v in instance._vectors.values()]
                if existing_texts:
                    backend._build_vocab(existing_texts)

        # Rebuild FAISS index if needed
        if instance.use_faiss and instance._embeddings:
            instance._initialize_faiss()
            if instance._faiss_index is not None:
                try:
                    import faiss  # noqa: F401
                    import numpy as np
                except ImportError as e:
                    raise VectorMemoryError(
                        f"FAISS dependencies not available: {e}. Install with: pip install faiss-cpu numpy",
                        context={"operation": "load", "use_faiss": True},
                    ) from e

                embeddings_list = [instance._embeddings[vid] for vid in instance._vectors.keys()]
                if embeddings_list:
                    embedding_array = np.array(embeddings_list, dtype=np.float32)
                    instance._faiss_index.add(embedding_array)

        return instance


class SentenceTransformerBackend(EmbeddingBackend):
    """Sentence transformers embedding backend."""

    def __init__(self, model: Any) -> None:
        """Initialize with sentence transformer model.

        Args:
            model: SentenceTransformer model instance
        """
        self.model = model

    def embed(self, text: str) -> list[float]:
        """Generate embedding using sentence transformer."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        result = embedding.tolist()
        return [float(x) for x in result]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed using sentence transformer."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [[float(x) for x in e.tolist()] for e in embeddings]

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return int(self.model.get_sentence_embedding_dimension())


class OpenAIBackend(EmbeddingBackend):
    """OpenAI embedding backend."""

    def __init__(
        self, api_key: str, dimension: int = 1536, model: str = "text-embedding-3-small"
    ) -> None:
        """Initialize OpenAI embedding backend.

        Args:
            api_key: OpenAI API key
            dimension: Expected embedding dimension
            model: OpenAI embedding model name
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise VectorMemoryError(
                "openai package not installed. Install with: pip install openai",
                context={"backend": "openai"},
            ) from None

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._dimension = dimension

    def embed(self, text: str) -> list[float]:
        """Generate embedding using OpenAI API."""
        response = self.client.embeddings.create(model=self.model, input=text)
        return list(response.data[0].embedding)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed using OpenAI API."""
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [list(item.embedding) for item in response.data]

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension
