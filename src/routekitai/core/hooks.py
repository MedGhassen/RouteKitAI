"""Policy hooks for RouteKit runtime."""

import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class PIIRedactionHook(BaseModel):
    """PII redaction hook for redacting sensitive information.

    Uses regex patterns to identify and redact PII like emails and phone numbers.
    """

    redact_emails: bool = Field(default=True, description="Redact email addresses")
    redact_phones: bool = Field(default=True, description="Redact phone numbers")
    redact_patterns: list[tuple[str, str]] = Field(
        default_factory=list, description="Custom (pattern, replacement) tuples"
    )
    replacement: str = Field(
        default="[REDACTED]", description="Replacement string for redacted content"
    )

    # Compiled regex patterns
    _email_pattern: re.Pattern[str] | None = None
    _phone_pattern: re.Pattern[str] | None = None

    def __init__(self, **kwargs: Any) -> None:
        """Initialize PII redaction hook."""
        super().__init__(**kwargs)
        if self.redact_emails:
            self._email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
        if self.redact_phones:
            # Matches various phone formats
            self._phone_pattern = re.compile(
                r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
            )

    def redact(self, text: str) -> str:
        """Redact PII from text.

        Args:
            text: Text to redact

        Returns:
            Text with PII redacted
        """
        result = text

        if self._email_pattern:
            result = self._email_pattern.sub(self.replacement, result)

        if self._phone_pattern:
            result = self._phone_pattern.sub(self.replacement, result)

        # Apply custom patterns
        for pattern, replacement in self.redact_patterns:
            result = re.sub(pattern, replacement, result)

        return result

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact PII from a dictionary.

        Args:
            data: Dictionary to redact

        Returns:
            Dictionary with PII redacted
        """
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                redacted[key] = self.redact(value)
            elif isinstance(value, dict):
                redacted[key] = self.redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self.redact(item) if isinstance(item, str) else item for item in value
                ]
            else:
                redacted[key] = value
        return redacted


class ToolFilter(BaseModel):
    """Tool allow/deny list filter."""

    allowed_tools: list[str] | None = Field(
        default=None, description="List of allowed tool names (None = allow all)"
    )
    denied_tools: list[str] = Field(default_factory=list, description="List of denied tool names")

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool is allowed, False otherwise
        """
        # Deny list takes precedence
        if tool_name in self.denied_tools:
            return False

        # If allow list is set, tool must be in it
        if self.allowed_tools is not None:
            return tool_name in self.allowed_tools

        # Default: allow if not in deny list
        return True


class ApprovalGate(BaseModel):
    """Approval gate for blocking tools until approved.

    Uses a callback function to determine if a tool should be approved.
    """

    approval_callback: Callable[[str, dict[str, Any]], bool] | None = Field(
        default=None, description="Callback(tool_name, tool_args) -> bool"
    )
    require_approval_for_permissions: list[str] = Field(
        default_factory=list, description="Permissions that require approval"
    )

    def requires_approval(
        self, tool_name: str, tool_args: dict[str, Any], tool_permissions: list[str]
    ) -> bool:
        """Check if a tool requires approval.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            tool_permissions: Tool permissions

        Returns:
            True if approval is required
        """
        # Check if tool has permissions that require approval
        if any(perm in self.require_approval_for_permissions for perm in tool_permissions):
            return True

        # Check callback if provided
        if self.approval_callback:
            return not self.approval_callback(tool_name, tool_args)

        return False

    def is_approved(self, tool_name: str, tool_args: dict[str, Any]) -> bool:
        """Check if a tool is approved.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments

        Returns:
            True if approved, False otherwise
        """
        if self.approval_callback:
            return self.approval_callback(tool_name, tool_args)
        return True  # Default: approved if no callback


class PolicyHooks(BaseModel):
    """Collection of policy hooks for runtime."""

    pii_redaction: PIIRedactionHook | None = Field(
        default=None, description="PII redaction hook for messages and tool arguments"
    )
    tool_filter: ToolFilter | None = Field(default=None, description="Tool allow/deny list")
    approval_gate: ApprovalGate | None = Field(default=None, description="Approval gate for tools")
