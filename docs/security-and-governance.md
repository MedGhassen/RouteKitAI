# Security and Governance

RouteKit provides built-in security and governance features to control agent behavior, protect sensitive data, and enforce policies.

## Policy Hooks

Policy hooks allow you to intercept and modify agent execution at various points. They are configured at the `Runtime` level and apply to all agents.

### PII Redaction

Automatically redact personally identifiable information (PII) from prompts, tool arguments, and trace logs.

```python
from routekit.core.hooks import PIIRedactionHook, PolicyHooks
from routekit.core.runtime import Runtime

# Create PII redaction hook
pii_hook = PIIRedactionHook(
    redact_emails=True,      # Redact email addresses
    redact_phones=True,      # Redact phone numbers
    replacement="[REDACTED]" # Custom replacement string
)

# Add custom patterns
pii_hook.redact_patterns = [
    (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[CARD]"),  # Credit cards
]

runtime = Runtime(
    policy_hooks=PolicyHooks(pii_redaction=pii_hook)
)
```

**Features:**
- Email addresses: `user@example.com` → `[REDACTED]`
- Phone numbers: `555-123-4567` → `[REDACTED]`
- Custom regex patterns
- Recursive redaction in nested dictionaries

### Tool Allow/Deny Lists

Control which tools can be executed at the agent or runtime level.

#### Agent-Level Filter

```python
from routekit.core.hooks import ToolFilter
from routekit.core.agent import Agent

# Only allow specific tools
agent = Agent(
    name="restricted_agent",
    model=model,
    tools=[tool1, tool2, tool3],
    tool_filter=ToolFilter(allowed_tools=["tool1", "tool2"])  # Only tool1 and tool2 allowed
)
```

#### Runtime-Level Filter

```python
from routekit.core.hooks import PolicyHooks, ToolFilter
from routekit.core.runtime import Runtime

# Deny specific tools globally
runtime = Runtime(
    policy_hooks=PolicyHooks(
        tool_filter=ToolFilter(denied_tools=["dangerous_tool", "network_tool"])
    )
)
```

**Priority:** Agent-level filters take precedence over runtime-level filters.

### Approval Gates

Require explicit approval before executing tools with certain permissions.

```python
from routekit.core.hooks import ApprovalGate, PolicyHooks
from routekit.core.runtime import Runtime

def approval_callback(tool_name: str, tool_args: dict) -> bool:
    """Return True if tool is approved, False otherwise."""
    # Check against approval database, user input, etc.
    if tool_name == "network_tool":
        # Require manual approval for network tools
        return check_approval_database(tool_name, tool_args)
    return True  # Auto-approve other tools

runtime = Runtime(
    policy_hooks=PolicyHooks(
        approval_gate=ApprovalGate(
            require_approval_for_permissions=["network", "filesystem"],
            approval_callback=approval_callback,
        )
    )
)
```

**Use Cases:**
- Block network access unless explicitly approved
- Require human review for file system operations
- Integrate with external approval systems

## Async Runtime Improvements

### Cancellation Support

Cancel long-running agent executions gracefully.

```python
import asyncio
from routekit.core.runtime import Runtime

runtime = Runtime()
runtime.register_agent(agent)

# Create a task that can be cancelled
task = asyncio.create_task(
    runtime.run("agent_name", "prompt")
)

# Cancel after 5 seconds
await asyncio.sleep(5)
task.cancel()

try:
    result = await task
except asyncio.CancelledError:
    print("Execution cancelled")
```

### Exponential Backoff Retry

Automatic retry with exponential backoff for failed tool executions.

```python
runtime = Runtime(
    max_retries=3,              # Maximum retry attempts
    retry_backoff_base=1.0,     # Base delay in seconds
    retry_backoff_max=60.0,     # Maximum delay cap
)
```

**Backoff Formula:** `delay = min(base * (2^attempt), max)`

- Attempt 1: 1.0s delay
- Attempt 2: 2.0s delay
- Attempt 3: 4.0s delay
- Capped at 60.0s maximum

### Structured Timeouts

Configure timeouts at multiple levels:

```python
# Runtime-level default timeout
runtime = Runtime(timeout=30.0)  # 30 seconds default

# Tool-level timeout (takes precedence)
tool = Tool(
    name="slow_tool",
    timeout=60.0,  # 60 seconds for this tool
    ...
)
```

## Replay Robustness

The replay system provides deterministic re-execution of agent runs for testing and debugging.

### Basic Replay

```python
# Original run
result = await runtime.run("agent_name", "prompt")
trace_id = result.trace_id

# Replay the same run
replayed = await runtime.replay(trace_id, "agent_name")
assert replayed.output.content == result.output.content
```

### Replay Options

```python
# Replay with output verification
replayed = await runtime.replay(
    trace_id,
    "agent_name",
    verify_output=True,  # Verify output matches original
    strict=True          # Raise error on mismatch
)

# Replay without strict checking (warnings only)
replayed = await runtime.replay(
    trace_id,
    "agent_name",
    verify_output=True,
    strict=False  # Log warnings but continue
)
```

### Replay Mismatch Handling

Replay detects and reports mismatches:

- **Agent mismatch**: Trace was for different agent
- **Step mismatch**: Expected step not found in trace
- **Output mismatch**: Replay output differs from original

```python
from routekit.core.errors import ReplayMismatchError

try:
    result = await runtime.replay(trace_id, "agent_name", strict=True)
except ReplayMismatchError as e:
    print(f"Replay failed: {e}")
```

## Best Practices

1. **Always enable PII redaction** in production to protect user data
2. **Use deny lists** for tools that should never be executed
3. **Implement approval gates** for high-risk permissions (network, filesystem)
4. **Set appropriate timeouts** to prevent runaway executions
5. **Use replay for testing** to ensure deterministic behavior
6. **Monitor trace files** for security audit trails

## Example: Secure Agent Configuration

```python
from routekit.core.agent import Agent
from routekit.core.hooks import (
    ApprovalGate,
    PIIRedactionHook,
    PolicyHooks,
    ToolFilter,
)
from routekit.core.runtime import Runtime
from routekit.providers.openai import OpenAIChatModel

# Create model
model = OpenAIChatModel(name="gpt-4", api_key=os.getenv("OPENAI_API_KEY"))

# Create agent with restricted tools
agent = Agent(
    name="secure_agent",
    model=model,
    tools=[safe_tool1, safe_tool2],
    tool_filter=ToolFilter(allowed_tools=["safe_tool1", "safe_tool2"]),
)

# Configure runtime with security hooks
def network_approval(tool_name: str, tool_args: dict) -> bool:
    # Check approval system
    return check_network_approval(tool_name)

runtime = Runtime(
    timeout=30.0,
    max_retries=3,
    retry_backoff_base=1.0,
    retry_backoff_max=60.0,
    policy_hooks=PolicyHooks(
        pii_redaction=PIIRedactionHook(redact_emails=True, redact_phones=True),
        tool_filter=ToolFilter(denied_tools=["dangerous_tool"]),
        approval_gate=ApprovalGate(
            require_approval_for_permissions=["network"],
            approval_callback=network_approval,
        ),
    ),
)

runtime.register_agent(agent)
result = await runtime.run("secure_agent", "User prompt with email@example.com")
```
