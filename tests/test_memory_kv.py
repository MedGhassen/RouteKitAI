"""Tests for KV memory."""

import pytest

from routekitai.memory.kv import KVMemory


@pytest.mark.asyncio
async def test_kv_memory_get_set() -> None:
    """Test basic get/set operations."""
    memory = KVMemory()

    # Set and get
    await memory.set("key1", "value1")
    assert await memory.get("key1") == "value1"

    # Overwrite
    await memory.set("key1", "value2")
    assert await memory.get("key1") == "value2"

    # Get non-existent key
    assert await memory.get("nonexistent") is None


@pytest.mark.asyncio
async def test_kv_memory_complex_values() -> None:
    """Test storing complex values."""
    memory = KVMemory()

    # Store dict
    await memory.set("dict_key", {"nested": {"value": 123}})
    result = await memory.get("dict_key")
    assert result == {"nested": {"value": 123}}

    # Store list
    await memory.set("list_key", [1, 2, 3])
    assert await memory.get("list_key") == [1, 2, 3]
