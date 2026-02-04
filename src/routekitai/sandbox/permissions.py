"""Permission management for tool execution."""

from enum import StrEnum

from pydantic import BaseModel, Field

from routekitai.core.tool import ToolPermission


class PermissionLevel(StrEnum):
    """Permission levels for sandbox execution."""

    NONE = "none"
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    FULL = "full"


class PermissionManager(BaseModel):
    """Manages permissions for tool execution.

    Guards tool execution by checking permissions before allowing tool calls.
    """

    permissions: dict[str, PermissionLevel] = Field(
        default_factory=dict, description="Permission mappings (tool_name -> level)"
    )
    default_level: PermissionLevel = Field(
        default=PermissionLevel.NONE, description="Default permission level"
    )

    def check_permission(self, permission: ToolPermission, resource: str) -> bool:
        """Check if permission is granted.

        Args:
            permission: Tool permission type
            resource: Resource identifier (typically tool name)

        Returns:
            True if permission granted, False otherwise
        """
        # Check explicit permission
        if resource in self.permissions:
            level = self.permissions[resource]
            if level == PermissionLevel.NONE:
                return False
            # For now, any non-NONE level grants permission
            # Can be refined based on permission type
            return True

        # Check default level
        return self.default_level != PermissionLevel.NONE

    def grant_permission(self, resource: str, level: PermissionLevel) -> None:
        """Grant permission to resource.

        Args:
            resource: Resource identifier (typically tool name)
            level: Permission level
        """
        self.permissions[resource] = level

    def revoke_permission(self, resource: str) -> None:
        """Revoke permission from resource.

        Args:
            resource: Resource identifier
        """
        if resource in self.permissions:
            del self.permissions[resource]
