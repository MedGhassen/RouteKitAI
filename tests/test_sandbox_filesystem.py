"""Tests for filesystem sandbox."""

import tempfile
from pathlib import Path

import pytest

from routekitai.sandbox.filesystem import FilesystemSandbox, FilesystemSandboxError


@pytest.mark.asyncio
async def test_filesystem_sandbox_check_path() -> None:
    """Test path checking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = FilesystemSandbox(
            allowed_paths=[Path(tmpdir)],
            sandbox_root=Path(tmpdir),
        )

        test_path = Path(tmpdir) / "test.txt"
        assert sandbox.check_path(test_path, "read") is True
        assert sandbox.check_path(test_path, "write") is True


@pytest.mark.asyncio
async def test_filesystem_sandbox_read_only() -> None:
    """Test read-only path restrictions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        read_only_dir = Path(tmpdir) / "readonly"
        read_only_dir.mkdir()

        sandbox = FilesystemSandbox(
            allowed_paths=[Path(tmpdir)],
            read_only_paths=[read_only_dir],
        )

        test_file = read_only_dir / "test.txt"
        assert sandbox.check_path(test_file, "read") is True
        assert sandbox.check_path(test_file, "write") is False
        assert sandbox.check_path(test_file, "delete") is False


@pytest.mark.asyncio
async def test_filesystem_sandbox_execute_operations() -> None:
    """Test filesystem operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = FilesystemSandbox(
            allowed_paths=[Path(tmpdir)],
            sandbox_root=Path(tmpdir),
        )

        test_file = Path(tmpdir) / "test.txt"

        # Write
        result = await sandbox.execute_operation(test_file, "write", content="Hello, World!")
        assert result["success"] is True
        assert test_file.exists()

        # Read
        content = await sandbox.execute_operation(test_file, "read")
        assert content == "Hello, World!"

        # Exists
        exists = await sandbox.execute_operation(test_file, "exists")
        assert exists is True

        # Delete
        result = await sandbox.execute_operation(test_file, "delete")
        assert result["success"] is True
        assert not test_file.exists()


@pytest.mark.asyncio
async def test_filesystem_sandbox_blocked_path() -> None:
    """Test blocked path operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        blocked_dir = Path(tmpdir) / "blocked"
        blocked_dir.mkdir()

        sandbox = FilesystemSandbox(
            allowed_paths=[Path(tmpdir) / "allowed"],
        )

        blocked_file = blocked_dir / "test.txt"
        with pytest.raises(FilesystemSandboxError):
            await sandbox.execute_operation(blocked_file, "write", content="test")
