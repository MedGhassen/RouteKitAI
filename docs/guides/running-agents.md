# Running agents

How to run agents: one-off `agent.run()`, streaming, and using the `Runtime` directly.

## Using `Agent.run()`

The simplest way to run an agent is to create an `Agent` and call `run()`:

```python
from routekitai import Agent
from routekitai.providers.local import FakeModel

model = FakeModel(name="test")
model.add_response("Done.")
agent = Agent(name="my_agent", model=model, tools=[])

result = await agent.run("Do something")
# result.output   — final Message
# result.trace_id — ID for this run
# result.messages — full conversation
# result.final_state — agent state at end
```

- The agent creates an internal `Runtime` and registers itself, so you don’t need to manage a runtime for basic use.
- Traces are written to `.routekit/traces/` by default. To use another directory, pass `trace_dir` when creating the agent:

  ```python
  from pathlib import Path
  agent = Agent(name="my_agent", model=model, tools=[], trace_dir=Path("/tmp/my_traces"))
  ```

## Streaming: `agent.run_stream()`

For real-time updates (e.g. progress or trace events), use `run_stream()`:

```python
async for event in agent.run_stream("Long task"):
    if event["type"] == "trace_event":
        print("Event:", event["data"].get("type"))
    elif event["type"] == "progress_update":
        print("Progress:", event["data"].get("progress_percent"), "%")
    elif event["type"] == "result":
        result = event["result"]
        print("Output:", result.output.content)
```

Events include:

- **`trace_event`** — Raw trace event (e.g. step_started, tool_called).
- **`progress_update`** — Progress info (e.g. `progress_percent`).
- **`result`** — Final `RunResult` (only in the last event).

## Using `Runtime` directly

When you need multiple agents, shared hooks, or a custom policy (e.g. graph, supervisor), use a `Runtime` and register agents:

```python
from pathlib import Path
from routekitai.core.runtime import Runtime
from routekitai.core.agent import Agent

runtime = Runtime(trace_dir=Path(".routekit/traces"))
runtime.register_agent(agent1)
runtime.register_agent(agent2)

result = await runtime.run("agent1", "Prompt", policy=some_policy)
```

- **`runtime.run(agent_name, prompt, policy=..., **kwargs)`** — Runs the named agent with the given prompt and optional policy.
- **`runtime.replay(trace_id, agent_name)`** — Replays a trace (requires `trace_dir` set). See [Tracing and replay](tracing-and-replay.md) for details.

You can pass **policy hooks** (PII redaction, tool filter, approval gate) on the runtime so they apply to all runs:

```python
from routekitai.core.hooks import PolicyHooks, PIIRedactionHook

runtime = Runtime(
    trace_dir=Path(".routekit/traces"),
    policy_hooks=PolicyHooks(pii_redaction=PIIRedactionHook(redact_emails=True)),
)
```

## Policies

By default, an agent uses a **ReAct**-style policy (reasoning and acting in a loop). You can pass a different policy when creating the agent or when calling `runtime.run()`:

- **ReActPolicy** — Model can call tools in a loop until it returns a final answer.
- **FunctionCallingPolicy** — Strict function-calling mode.
- **GraphPolicy** — Execute a graph workflow; see [Graph workflows](graph-workflows.md).
- **SupervisorPolicy** — One agent delegates to others.
- **PlanExecutePolicy** — Plan first, then execute.

Example with a custom policy on the agent:

```python
from routekitai.core.policies import ReActPolicy

agent = Agent(
    name="my_agent",
    model=model,
    tools=[...],
    policy=ReActPolicy(max_iterations=15),
)
```

## Timeouts and concurrency

- **Runtime** accepts `timeout` (default timeout for a run) and `max_concurrency` (parallel tool calls).
- **Tool** can set `timeout` for that tool’s execution.

See [Security & Governance](../security-and-governance.md) for timeouts, retries, and approval gates.
