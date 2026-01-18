"""Tests for network sandbox."""

import pytest

from routekit.sandbox.network import NetworkSandbox, NetworkSandboxError


@pytest.mark.asyncio
async def test_network_sandbox_check_request() -> None:
    """Test request checking."""
    sandbox = NetworkSandbox(
        allowed_hosts=["example.com"],
    )

    assert await sandbox.check_request("https://example.com/api") is True
    assert await sandbox.check_request("https://blocked.com/api") is False


@pytest.mark.asyncio
async def test_network_sandbox_blocked_hosts() -> None:
    """Test blocked hosts."""
    sandbox = NetworkSandbox(
        blocked_hosts=["malicious.com"],
    )

    assert await sandbox.check_request("https://example.com/api") is True
    assert await sandbox.check_request("https://malicious.com/api") is False


@pytest.mark.asyncio
async def test_network_sandbox_rate_limiting() -> None:
    """Test rate limiting."""
    import time

    sandbox = NetworkSandbox(
        rate_limit={"requests_per_minute": 2},
    )

    # Manually add requests to history to test rate limiting logic
    host = "example.com"
    now = time.time()
    sandbox._request_history[host] = [now, now]  # Two requests in history

    # Third request should be rate limited (within same minute)
    assert await sandbox.check_request("https://example.com/api") is False

    # After clearing history, should work again
    sandbox._request_history[host] = []
    assert await sandbox.check_request("https://example.com/api") is True


@pytest.mark.asyncio
async def test_network_sandbox_blocked_request() -> None:
    """Test blocked request execution."""
    sandbox = NetworkSandbox(
        allowed_hosts=["example.com"],
    )

    with pytest.raises(NetworkSandboxError):
        await sandbox.execute_request("https://blocked.com/api", "GET")
