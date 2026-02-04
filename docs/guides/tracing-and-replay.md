# Tracing and replay

Every agent run produces a **trace**: an immutable, append-only log of events. Traces are used for debugging, analytics, and **deterministic replay** (re-running a past execution with stubbed external calls).

## Where traces are stored

- By default, traces are written under **`.routekit/traces/`**.
- Each run has a **trace ID** (UUID); the trace file is `<trace_dir>/<trace_id>.jsonl`.
- You can set a custom directory when creating an agent or runtime:

  ```python
  from pathlib import Path
  agent = Agent(..., trace_dir=Path("/tmp/my_traces"))
  # or
  runtime = Runtime(trace_dir=Path("/tmp/my_traces"))
  ```

## What is recorded

Trace events include:

- `run_started` / `run_completed`
- `step_started` / `step_completed`
- `model_called` (inputs/outputs, token usage when available)
- `tool_called` / `tool_result`
- `error`

Traces are **immutable**: once a run finishes, the file is complete and not modified.

## Getting the trace ID

From code, every `RunResult` includes `trace_id`:

```python
result = await agent.run("Hello")
print(result.trace_id)  # e.g. "f98eb1b6-6eec-42df-b42a-021dc704620b"
```

Use this ID with the CLI or with `runtime.replay()`.

## CLI: view and analyze traces

The **routekitai** CLI can list, show, analyze, and search traces. Default trace directory is `.routekit/traces` unless overridden.

**View a trace** (table, timeline, steps, JSON, or raw JSONL):

```bash
routekitai trace <trace_id>
routekitai trace <trace_id> --format timeline
routekitai trace <trace_id> --format steps
routekitai trace <trace_id> --format json
routekitai trace <trace_id> --format raw
```

**Analyze metrics** (latency, token usage, cost when available):

```bash
routekitai trace-analyze <trace_id>
```

**Search** across traces:

```bash
routekitai trace-search "error"
routekitai trace-search "model" --trace-id <trace_id>
routekitai trace-search "tool" --event-type tool_called
```

**Replay** a trace (re-run with stubbed model/tool responses from the trace):

```bash
routekitai replay <trace_id> --agent <agent_name>
```

**Web UI** for browsing traces:

```bash
routekitai serve
# Open http://localhost:8080 (or --port)
```

Install the **`[ui]`** extra if needed: `pip install "RouteKitAI[ui]"`.

## Replay from code

Replay runs the same flow as the original trace but uses **stubbed** model and tool responses from the trace (no real API or tool calls). Useful for tests and regression checks.

```python
from pathlib import Path
from routekitai.core.runtime import Runtime

runtime = Runtime(trace_dir=Path(".routekit/traces"))
runtime.register_agent(my_agent)

replay_result = await runtime.replay(trace_id="<trace_id>", agent_name="my_agent")
# replay_result should match the original run’s outputs when stubs are used
```

- **`trace_dir`** must be set on the runtime; the trace file must exist in that directory.
- Replay uses the same policy and agent name as the original run (from the trace). A **ReplayMismatchError** is raised if execution diverges from the trace (e.g. different number of steps or tool calls).

## Best practices

- **Retention** — Implement a policy for old trace files (e.g. delete or archive after N days) if you trace heavily.
- **Sensitive data** — Use PII redaction and tool `redact_fields` so traces don’t contain secrets; see [Security & Governance](../security-and-governance.md).
- **Tests** — Record a trace from a “golden” run, then use `runtime.replay()` in tests to guard against regressions.
