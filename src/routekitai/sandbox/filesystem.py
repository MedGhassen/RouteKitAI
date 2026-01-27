"""Filesystem sandbox for tool execution."""

import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from routekitai.core.errors import RuntimeError as RouteKitRuntimeError


class FilesystemSandboxError(RouteKitRuntimeError):
    """Error raised by filesystem sandbox operations."""

    pass


class FilesystemSandbox(BaseModel):
    """Filesystem sandbox for controlling tool file access.

    Provides path restrictions, read-only mounts, and basic isolation.
    """

    allowed_paths: list[Path] = Field(default_factory=list, description="Allowed paths")
    read_only_paths: list[Path] = Field(default_factory=list, description="Read-only paths")
    sandbox_root: Path | None = Field(default=None, description="Sandbox root directory")

    def check_path(self, path: Path, operation: str = "read") -> bool:
        """Check if path operation is allowed.

        Args:
            path: File path
            operation: Operation type (read, write, delete)

        Returns:
            True if allowed, False otherwise
        """
        # Resolve path to absolute
        try:
            resolved_path = path.resolve()
        except (OSError, RuntimeError):
            return False

        # If sandbox_root is set, ensure path is within it
        if self.sandbox_root:
            try:
                sandbox_resolved = self.sandbox_root.resolve()
                # Check if path is within sandbox
                if not str(resolved_path).startswith(str(sandbox_resolved)):
                    return False
            except (OSError, RuntimeError):
                return False

        # Check if path is in allowed paths
        if self.allowed_paths:
            is_allowed = False
            for allowed in self.allowed_paths:
                try:
                    allowed_resolved = allowed.resolve()
                    if str(resolved_path).startswith(str(allowed_resolved)):
                        is_allowed = True
                        break
                except (OSError, RuntimeError):
                    continue
            if not is_allowed:
                return False

        # Check if path is read-only for write/delete operations
        if operation in ("write", "delete"):
            for read_only in self.read_only_paths:
                try:
                    read_only_resolved = read_only.resolve()
                    if str(resolved_path).startswith(str(read_only_resolved)):
                        return False
                except (OSError, RuntimeError):
                    continue

        return True

    async def execute_operation(self, path: Path, operation: str, **kwargs: Any) -> Any:
        """Execute filesystem operation through sandbox.

        Args:
            path: File path
            operation: Operation type (read, write, delete, list)
            **kwargs: Operation parameters (content for write, etc.)

        Returns:
            Operation result

        Raises:
            FilesystemSandboxError: If operation is not allowed or fails
        """
        if not self.check_path(path, operation):
            raise FilesystemSandboxError(
                f"Operation '{operation}' not allowed on path: {path}",
                context={"path": str(path), "operation": operation},
            )

        try:
            if operation == "read":
                return path.read_text(encoding="utf-8")
            elif operation == "write":
                content = kwargs.get("content", "")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return {"success": True, "path": str(path)}
            elif operation == "delete":
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
                return {"success": True, "path": str(path)}
            elif operation == "list":
                if path.is_dir():
                    return [str(p) for p in path.iterdir()]
                return []
            elif operation == "exists":
                return path.exists()
            elif operation == "mkdir":
                path.mkdir(parents=True, exist_ok=True)
                return {"success": True, "path": str(path)}
            else:
                raise FilesystemSandboxError(
                    f"Unknown operation: {operation}", context={"operation": operation}
                )
        except Exception as e:
            raise FilesystemSandboxError(
                f"Filesystem operation failed: {e}",
                context={"path": str(path), "operation": operation},
            ) from e
