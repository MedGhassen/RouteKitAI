# Security and Governance

RouteKitAI provides built-in security and governance features to control agent behavior, protect sensitive data, and enforce policies. This guide covers all security features and best practices.

## Table of Contents

- [Policy Hooks](#policy-hooks)
- [PII Redaction](#pii-redaction)
- [Tool Filtering](#tool-filtering)
- [Approval Gates](#approval-gates)
- [Sandboxing](#sandboxing)
- [Timeouts and Retries](#timeouts-and-retries)
- [Trace Security](#trace-security)
- [Best Practices](#best-practices)

## Policy Hooks

Policy hooks allow you to intercept and modify agent execution at various points. They are configured at the `Runtime` level and apply to all agents.

### Hook Architecture

```python
class PolicyHooks(BaseModel):
    pii_redaction: PIIRedactionHook | None = None
    tool_filter: ToolFilter | None = None
    approval_gate: ApprovalGate | None = None
```

Hooks are executed in order:
1. PII Redaction (before trace recording)
2. Tool Filtering (before tool execution)
3. Approval Gate (before tool execution)

## PII Redaction

Automatically redact personally identifiable information (PII) from prompts, tool arguments, and trace logs.

### Basic Usage

```python
from routekitai.core.hooks import PIIRedactionHook, PolicyHooks
from routekitai.core.runtime import Runtime

# Create PII redaction hook
pii_hook = PIIRedactionHook(
    redact_emails=True,      # Redact email addresses
    redact_phones=True,      # Redact phone numbers
    replacement="[REDACTED]" # Custom replacement string
)

runtime = Runtime(
    policy_hooks=PolicyHooks(pii_redaction=pii_hook)
)
```

### Custom Patterns

Add custom regex patterns for domain-specific PII:

```python
pii_hook = PIIRedactionHook(
    redact_emails=True,
    redact_phones=True,
)

# Add custom patterns
pii_hook.redact_patterns = [
    (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[CARD]"),  # Credit cards
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),  # Social Security Numbers
    (r"\b[A-Z]{2}\d{6}\b", "[PASSPORT]"),  # Passport numbers
]

runtime = Runtime(
    policy_hooks=PolicyHooks(pii_redaction=pii_hook)
)
```

### Features

- **Email addresses**: `user@example.com` → `[REDACTED]`
- **Phone numbers**: `555-123-4567` → `[REDACTED]`
- **Custom regex patterns**: Match any pattern
- **Recursive redaction**: Works in nested dictionaries and lists
- **Trace integration**: Automatically redacts trace logs

### What Gets Redacted

PII redaction applies to:
- User prompts
- Tool arguments
- Model responses (optional)
- Trace event data
- Error messages

## Tool Filtering

Control which tools can be executed at the agent or runtime level.

### Agent-Level Filter

Restrict tools for a specific agent:

```python
from routekitai.core.hooks import ToolFilter
from routekitai.core.agent import Agent

# Only allow specific tools
agent = Agent(
    name="restricted_agent",
    model=model,
    tools=[tool1, tool2, tool3],
    tool_filter=ToolFilter(allowed_tools=["tool1", "tool2"])  # Only tool1 and tool2 allowed
)
```

### Runtime-Level Filter

Deny specific tools globally:

```python
from routekitai.core.hooks import PolicyHooks, ToolFilter
from routekitai.core.runtime import Runtime

# Deny specific tools globally
runtime = Runtime(
    policy_hooks=PolicyHooks(
        tool_filter=ToolFilter(denied_tools=["dangerous_tool", "network_tool"])
    )
)
```

### Priority

Agent-level filters take precedence over runtime-level filters. If an agent has a filter, it overrides the runtime filter.

### Use Cases

- **Development**: Restrict tools during testing
- **Production**: Deny dangerous tools globally
- **Multi-tenant**: Different tool sets per tenant
- **Compliance**: Enforce tool usage policies

## Approval Gates

Require explicit approval before executing tools with certain permissions.

### Basic Setup

```python
from routekitai.core.hooks import ApprovalGate, PolicyHooks
from routekitai.core.runtime import Runtime

def approval_callback(tool_name: str, tool_args: dict) -> bool:
    """Return True if tool is approved, False otherwise."""
    # Check against approval database, user input, etc.
    if tool_name == "network_tool":
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

### Permission-Based Approval

Tools can declare permissions:

```python
from routekitai.core.tool import ToolPermission

class NetworkTool(Tool):
    permissions = [ToolPermission.NETWORK]
    ...
```

The approval gate checks these permissions:

```python
approval_gate = ApprovalGate(
    require_approval_for_permissions=["network", "filesystem"],
    approval_callback=my_callback,
)
```

### Use Cases

- **Network access**: Block network tools unless explicitly approved
- **File system operations**: Require human review for file writes
- **External API calls**: Approve API calls based on cost/risk
- **Integration**: Connect to external approval systems

## Sandboxing

Sandboxing provides isolation for tool execution. (Note: Sandboxing is planned for future releases.)

### Filesystem Sandbox

Control file system access:

```python
from routekitai.sandbox.filesystem import FilesystemSandbox

sandbox = FilesystemSandbox(
    allowed_paths=[Path("/safe/directory")],
    read_only_paths=[Path("/readonly")],
    sandbox_root=Path("/sandbox"),
)
```

### Network Sandbox

Control network access:

```python
from routekitai.sandbox.network import NetworkSandbox

sandbox = NetworkSandbox(
    allowed_hosts=["api.example.com"],
    blocked_hosts=["dangerous-site.com"],
    rate_limit={"requests_per_minute": 60},
)
```

## Timeouts and Retries

### Timeouts

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

### Retries

Automatic retry with exponential backoff:

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

### Cancellation

Cancel long-running executions gracefully:

```python
import asyncio
from routekitai.core.runtime import Runtime

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

## Trace Security

Traces contain sensitive information. Protect them accordingly.

### Trace Storage

- **Local storage**: Traces stored in `.RouteKitAI/traces/` by default
- **Encryption**: Encrypt trace files if they contain sensitive data
- **Access control**: Restrict file system permissions
- **Retention**: Implement trace retention policies

### Trace Redaction

PII redaction automatically applies to traces:

```python
runtime = Runtime(
    trace_dir=Path(".RouteKitAI/traces"),
    policy_hooks=PolicyHooks(
        pii_redaction=PIIRedactionHook(redact_emails=True, redact_phones=True)
    )
)
```

### Trace Sharing

Before sharing traces:
1. Review for sensitive data
2. Redact PII if needed
3. Remove API keys and credentials
4. Anonymize user data

## Best Practices

### 1. Always Enable PII Redaction in Production

```python
runtime = Runtime(
    policy_hooks=PolicyHooks(
        pii_redaction=PIIRedactionHook(
            redact_emails=True,
            redact_phones=True,
        )
    )
)
```

### 2. Use Deny Lists for Dangerous Tools

```python
runtime = Runtime(
    policy_hooks=PolicyHooks(
        tool_filter=ToolFilter(
            denied_tools=["delete_file", "format_disk", "shutdown_system"]
        )
    )
)
```

### 3. Implement Approval Gates for High-Risk Permissions

```python
def require_approval(tool_name: str, tool_args: dict) -> bool:
    # Check approval system
    return check_approval_system(tool_name, tool_args)

runtime = Runtime(
    policy_hooks=PolicyHooks(
        approval_gate=ApprovalGate(
            require_approval_for_permissions=["network", "filesystem"],
            approval_callback=require_approval,
        )
    )
)
```

### 4. Set Appropriate Timeouts

```python
runtime = Runtime(
    timeout=30.0,  # Prevent runaway executions
)
```

### 5. Use Replay for Testing

```python
# Replay production traces in test environment
replayed = await runtime.replay(trace_id, "agent_name")
```

### 6. Monitor Trace Files

- Regularly review trace files for security issues
- Implement trace retention policies
- Encrypt sensitive traces
- Restrict access to trace directories

### 7. Secure API Keys

- Never commit API keys to version control
- Use environment variables or secret management
- Rotate keys regularly
- Use different keys for dev/staging/prod

## Complete Example

```python
import os
from pathlib import Path
from routekitai.core.agent import Agent
from routekitai.core.hooks import (
    ApprovalGate,
    PIIRedactionHook,
    PolicyHooks,
    ToolFilter,
)
from routekitai.core.runtime import Runtime
from routekitai.providers.openai import OpenAIChatModel

# Create model with secure API key handling
model = OpenAIChatModel(
    name="gpt-4",
    api_key=os.getenv("OPENAI_API_KEY")  # Never hardcode!
)

# Create agent with restricted tools
agent = Agent(
    name="secure_agent",
    model=model,
    tools=[safe_tool1, safe_tool2],
    tool_filter=ToolFilter(allowed_tools=["safe_tool1", "safe_tool2"]),
)

# Approval callback
def network_approval(tool_name: str, tool_args: dict) -> bool:
    # Check approval system
    return check_network_approval(tool_name)

# Configure runtime with security hooks
runtime = Runtime(
    timeout=30.0,
    max_retries=3,
    retry_backoff_base=1.0,
    retry_backoff_max=60.0,
    trace_dir=Path(".RouteKitAI/traces"),
    policy_hooks=PolicyHooks(
        pii_redaction=PIIRedactionHook(
            redact_emails=True,
            redact_phones=True,
        ),
        tool_filter=ToolFilter(
            denied_tools=["dangerous_tool"]
        ),
        approval_gate=ApprovalGate(
            require_approval_for_permissions=["network"],
            approval_callback=network_approval,
        ),
    ),
)

runtime.register_agent(agent)
result = await runtime.run("secure_agent", "User prompt with email@example.com")
```

## Security Checklist

- [ ] PII redaction enabled in production
- [ ] Tool deny lists configured
- [ ] Approval gates for high-risk permissions
- [ ] Timeouts set appropriately
- [ ] API keys stored securely
- [ ] Trace files protected
- [ ] Access control implemented
- [ ] Regular security reviews scheduled

## Reporting Security Issues

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue
2. Email security concerns to: security@RouteKitAI.dev (or your security contact)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We take security seriously and will respond promptly to all reports.
