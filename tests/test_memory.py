"""Tests for memory implementations."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest

from routekit.core.memory import Memory
from routekit.memory.episodic import EpisodicMemory
from routekit.memory.retrieval import RetrievalMemory
from routekit.memory.working import WorkingMemory


@pytest.mark.asyncio
async def test_working_memory() -> None:
    """Test WorkingMemory basic operations."""
    memory = WorkingMemory()

    # Test get/set
    await memory.set("key1", "value1")
    assert await memory.get("key1") == "value1"
    assert await memory.get("nonexistent") is None

    # Test append
    await memory.append({"type": "event", "data": "test"})
    events = memory.get_events()
    assert len(events) == 1
    assert events[0]["type"] == "event"

    # Test clear
    memory.clear()
    assert await memory.get("key1") is None
    assert len(memory.get_events()) == 0


@pytest.mark.asyncio
async def test_episodic_memory_persistence() -> None:
    """Test EpisodicMemory SQLite persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Create memory and store episodes
        memory1 = EpisodicMemory(db_path=db_path)
        try:
            await memory1.set("ep1", {"content": "Episode 1", "metadata": {"type": "test"}})
            await memory1.append({"content": "Episode 2", "metadata": {"type": "test"}})
            memory1.close()  # Ensure connections are closed on Windows

            # Verify persistence: create new instance and check data
            memory2 = EpisodicMemory(db_path=db_path)
            try:
                ep1 = await memory2.get("ep1")
                assert ep1 is not None
                # Content is stored as dict with "content" key
                if isinstance(ep1["content"], dict):
                    assert ep1["content"].get("content") == "Episode 1"
                else:
                    assert ep1["content"] == "Episode 1"

                # Test get_recent
                recent = await memory2.get_recent(limit=5)
                assert len(recent) >= 2
            finally:
                memory2.close()  # Ensure connections are closed on Windows
        finally:
            memory1.close()  # Ensure connections are closed on Windows


@pytest.mark.asyncio
async def test_episodic_memory_search() -> None:
    """Test EpisodicMemory search functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        memory = EpisodicMemory(db_path=db_path)
        try:
            # Store episodes
            await memory.append({"content": "Python programming tutorial", "metadata": {}})
            await memory.append({"content": "JavaScript web development", "metadata": {}})
            await memory.append({"content": "Python data science", "metadata": {}})

            # Search
            results = await memory.search("Python", k=5)
            assert len(results) == 2
            assert all("Python" in str(r["content"]) for r in results)
        finally:
            memory.close()  # Ensure connections are closed on Windows


@pytest.mark.asyncio
async def test_retrieval_memory_tfidf() -> None:
    """Test RetrievalMemory with TF-IDF."""
    memory = RetrievalMemory(use_tfidf=True)

    # Add documents
    await memory.set("doc1", {"content": "Python programming language"})
    await memory.set("doc2", {"content": "JavaScript web development"})
    await memory.set("doc3", {"content": "Python data science and machine learning"})

    # Search
    results = await memory.search("Python", k=2)
    assert len(results) > 0
    assert all("score" in r for r in results)
    # Results should be sorted by score
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_retrieval_memory_substring() -> None:
    """Test RetrievalMemory with substring search."""
    memory = RetrievalMemory(use_tfidf=False)

    # Add documents
    await memory.set("doc1", {"content": "Python programming"})
    await memory.set("doc2", {"content": "JavaScript development"})
    await memory.set("doc3", {"content": "Python data science"})

    # Search
    results = await memory.search("Python", k=5)
    assert len(results) == 2
    assert all("Python" in str(r.get("content", "")) for r in results)


@pytest.mark.asyncio
async def test_retrieval_memory_append() -> None:
    """Test RetrievalMemory append functionality."""
    memory = RetrievalMemory(use_tfidf=False)  # Use substring for simpler test

    await memory.append({"content": "New document", "metadata": {"source": "test"}})

    # Verify document was added
    assert len(memory._documents) > 0

    # Should be able to search for the appended document
    results = await memory.search("document", k=1)
    assert len(results) > 0, f"Search should find document. Documents: {memory._documents}"
    # Verify the appended document is in results
    assert any("New document" in str(r.get("content", "")) for r in results)

    # Also test get by ID
    doc_id = results[0].get("id")
    if doc_id:
        retrieved = await memory.get(doc_id)
        assert retrieved is not None
        assert "New document" in str(retrieved.get("content", ""))


@pytest.mark.asyncio
async def test_memory_in_agent_state() -> None:
    """Test that memory is accessible in agent state."""
    from routekit.core.agent import Agent
    from routekit.core.message import Message
    from routekit.core.model import Model, ModelResponse, Usage
    from routekit.core.policy import ModelAction, Policy
    from routekit.core.policy_adapter import PolicyAdapter
    from routekit.core.runtime import Runtime

    class MockModel(Model):
        def __init__(self) -> None:
            super().__init__()
            object.__setattr__(self, "_name", "mock")
            object.__setattr__(self, "provider", "test")

        async def chat(self, messages, tools=None, stream=False, **kwargs):
            return ModelResponse(
                content="Response",
                usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

    class MemoryAwarePolicy(Policy):
        async def plan(self, state: dict[str, Any]) -> list:
            memory = state.get("memory")
            if memory:
                # Test memory access
                await memory.set("test_key", "test_value")
                value = await memory.get("test_key")
                assert value == "test_value"
            messages = state.get("messages", [])
            if not messages:
                messages = [Message.user("Hello")]
            return [ModelAction(messages=messages)]

    memory = WorkingMemory()
    model = MockModel()

    # Create a concrete agent implementation
    class TestAgent(Agent):
        async def run(self, prompt: str, **kwargs: Any) -> Any:
            # Not used in this test - runtime handles execution
            raise NotImplementedError("Use runtime.run() instead")

    agent = TestAgent(name="test_agent", model=model, tools=[], memory=memory)

    runtime = Runtime()
    runtime.register_agent(agent)

    policy = PolicyAdapter(MemoryAwarePolicy())
    result = await runtime.run("test_agent", "Hello", policy=policy)

    # Verify memory was used
    assert await memory.get("test_key") == "test_value"
