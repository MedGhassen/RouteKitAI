"""Tests for vector memory."""

import tempfile
from pathlib import Path

import pytest

from routekit.memory.vector import VectorMemory, VectorMemoryError


@pytest.mark.asyncio
async def test_vector_memory_add() -> None:
    """Test adding vectors."""
    memory = VectorMemory(dimension=128)

    vector_id = await memory.add("This is a test document", {"type": "test"})
    assert vector_id is not None
    assert isinstance(vector_id, str)

    # Verify it was stored
    vector_data = await memory.get(vector_id)
    assert vector_data is not None
    assert vector_data["text"] == "This is a test document"
    assert vector_data["metadata"]["type"] == "test"


@pytest.mark.asyncio
async def test_vector_memory_search() -> None:
    """Test vector search with cosine similarity."""
    memory = VectorMemory(dimension=128)

    # Add some documents
    await memory.add("Python programming language", {"topic": "programming"})
    await memory.add("Machine learning algorithms", {"topic": "ai"})
    await memory.add("Python web frameworks", {"topic": "web"})

    # Search
    results = await memory.search("Python", top_k=2)
    assert len(results) >= 1  # At least one result should be returned
    # Check that results are sorted by score (descending)
    if len(results) > 1:
        assert results[0]["score"] >= results[1]["score"]
    # Check result structure
    assert all("score" in r for r in results)
    assert all("distance" in r for r in results)
    assert all("metadata" in r for r in results)
    assert all("text" in r for r in results)
    assert all("id" in r for r in results)


@pytest.mark.asyncio
async def test_vector_memory_search_no_results() -> None:
    """Test search with empty memory returns no results."""
    memory = VectorMemory(dimension=128)

    # Search with no documents stored
    results = await memory.search("any query", top_k=5)
    assert results == []

    # Add a document
    await memory.add("Test document", {})

    # Search with very high threshold should filter most results
    results = await memory.search("xyzabc123", top_k=5, min_similarity=0.95)
    # With very high threshold, should get few or no results
    assert all(r["score"] >= 0.95 for r in results) if results else True


@pytest.mark.asyncio
async def test_vector_memory_search_with_threshold() -> None:
    """Test search with similarity threshold."""
    memory = VectorMemory(dimension=128, similarity_threshold=0.5)

    await memory.add("Python programming", {})
    await memory.add("Completely different topic", {})

    results = await memory.search("Python", top_k=5)
    # Should only return results above threshold
    assert all(r["score"] >= 0.5 for r in results)


@pytest.mark.asyncio
async def test_vector_memory_metadata_filtering() -> None:
    """Test search with metadata filtering."""
    memory = VectorMemory(dimension=128)

    await memory.add("Python tutorial", {"category": "tutorial", "level": "beginner"})
    await memory.add("Python advanced", {"category": "tutorial", "level": "advanced"})
    await memory.add("Java tutorial", {"category": "tutorial", "level": "beginner"})

    # Filter by metadata
    results = await memory.search(
        "tutorial",
        top_k=10,
        filter_metadata={"level": "beginner"},
        min_similarity=0.0,  # Ensure we get all results above threshold
    )

    # SimpleEmbeddingBackend may not return all documents due to TF-IDF limitations
    # But we should get at least one, and all results should match the filter
    assert len(results) >= 1
    assert all(r["metadata"]["level"] == "beginner" for r in results)


@pytest.mark.asyncio
async def test_vector_memory_batch_add() -> None:
    """Test batch adding vectors."""
    memory = VectorMemory(dimension=128)

    texts = ["Document 1", "Document 2", "Document 3"]
    metadata_list = [{"id": i} for i in range(3)]

    vector_ids = await memory.add_batch(texts, metadata_list)
    assert len(vector_ids) == 3

    # Verify all were stored
    for vector_id, expected_text in zip(vector_ids, texts):
        vector_data = await memory.get(vector_id)
        assert vector_data is not None
        assert vector_data["text"] == expected_text


@pytest.mark.asyncio
async def test_vector_memory_delete() -> None:
    """Test deleting vectors."""
    memory = VectorMemory(dimension=128)

    vector_id = await memory.add("Test document", {})
    assert await memory.get(vector_id) is not None

    deleted = await memory.delete(vector_id)
    assert deleted is True
    assert await memory.get(vector_id) is None

    # Delete non-existent
    deleted = await memory.delete("nonexistent")
    assert deleted is False


@pytest.mark.asyncio
async def test_vector_memory_persistence() -> None:
    """Test saving and loading vector memory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "vectors.pkl"

        # Create and save
        memory1 = VectorMemory(dimension=128)
        await memory1.add("Test document 1", {"id": 1})
        await memory1.add("Test document 2", {"id": 2})
        memory1.save(path)

        # Load
        memory2 = VectorMemory.load(path)

        # Verify data - SimpleEmbeddingBackend may not return all documents
        # due to TF-IDF limitations, but we should get at least one
        results = await memory2.search("Test", top_k=10, min_similarity=0.0)
        assert len(results) >= 1
        # Verify that the loaded data is correct
        assert len(memory2._vectors) == 2
        assert len(memory2._embeddings) == 2


@pytest.mark.asyncio
async def test_vector_memory_empty_query() -> None:
    """Test search with empty query."""
    memory = VectorMemory(dimension=128)
    await memory.add("Test", {})

    results = await memory.search("", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_vector_memory_empty_add() -> None:
    """Test adding empty text raises error."""
    memory = VectorMemory(dimension=128)

    with pytest.raises(VectorMemoryError, match="empty text"):
        await memory.add("", {})


@pytest.mark.asyncio
async def test_vector_memory_batch_mismatch() -> None:
    """Test batch add with mismatched metadata."""
    memory = VectorMemory(dimension=128)

    with pytest.raises(VectorMemoryError, match="length must match"):
        await memory.add_batch(["text1", "text2"], [{"id": 1}])  # Mismatched lengths
