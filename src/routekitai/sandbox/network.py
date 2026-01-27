"""Network sandbox for tool execution."""

import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from routekitai.core.errors import RuntimeError as RouteKitRuntimeError


class NetworkSandboxError(RouteKitRuntimeError):
    """Error raised by network sandbox operations."""

    pass


class NetworkSandbox(BaseModel):
    """Network sandbox for controlling tool network access.

    Provides allowlists, blocklists, and basic rate limiting.
    """

    allowed_hosts: list[str] = Field(default_factory=list, description="Allowed hostnames")
    blocked_hosts: list[str] = Field(default_factory=list, description="Blocked hostnames")
    rate_limit: dict[str, Any] = Field(default_factory=dict, description="Rate limit config")

    def __init__(self, **data: Any) -> None:
        """Initialize network sandbox."""
        super().__init__(**data)
        self._request_history: dict[str, list[float]] = defaultdict(list)

    def _extract_host(self, url: str) -> str:
        """Extract hostname from URL.

        Args:
            url: URL string

        Returns:
            Hostname
        """
        try:
            parsed = urlparse(url)
            return parsed.hostname or ""
        except Exception:
            return ""

    async def check_request(self, url: str, method: str = "GET") -> bool:
        """Check if network request is allowed.

        Args:
            url: Request URL
            method: HTTP method

        Returns:
            True if allowed, False otherwise
        """
        host = self._extract_host(url)
        if not host:
            return False

        # Check blocked hosts first
        if self.blocked_hosts:
            for blocked in self.blocked_hosts:
                if blocked in host or host in blocked:
                    return False

        # Check allowed hosts (if specified, must be in list)
        if self.allowed_hosts:
            is_allowed = False
            for allowed in self.allowed_hosts:
                if allowed in host or host in allowed:
                    is_allowed = True
                    break
            if not is_allowed:
                return False

        # Check rate limiting
        if self.rate_limit:
            requests_per_minute = self.rate_limit.get("requests_per_minute")
            if requests_per_minute:
                now = time.time()
                # Clean old requests (older than 1 minute)
                self._request_history[host] = [
                    timestamp for timestamp in self._request_history[host] if now - timestamp < 60
                ]
                # Check if limit exceeded
                if len(self._request_history[host]) >= requests_per_minute:
                    return False

        return True

    async def execute_request(self, url: str, method: str = "GET", **kwargs: Any) -> Any:
        """Execute network request through sandbox.

        Args:
            url: Request URL
            method: HTTP method
            **kwargs: Request parameters

        Returns:
            Response data

        Raises:
            NetworkSandboxError: If request is not allowed or fails
        """
        if not await self.check_request(url, method):
            raise NetworkSandboxError(
                f"Network request not allowed: {method} {url}",
                context={"url": url, "method": method},
            )

        # Record request for rate limiting
        host = self._extract_host(url)
        if host:
            self._request_history[host].append(time.time())

        # Execute request using httpx
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "content": response.text,
                    "json": response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else None,
                }
        except ImportError:
            raise NetworkSandboxError(
                "httpx is required for network requests. Install with: pip install httpx",
                context={"url": url, "method": method},
            ) from None
        except Exception as e:
            raise NetworkSandboxError(
                f"Network request failed: {e}", context={"url": url, "method": method}
            ) from e
