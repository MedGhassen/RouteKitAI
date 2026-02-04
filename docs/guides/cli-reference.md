# CLI reference

The RouteKitAI CLI is invoked as **`routekitai`**. Install with `pip install RouteKitAI` or `pip install "RouteKitAI[dev]"` for full CLI support.

Default trace directory: **`.routekit/traces`** (overridable per command where noted).

---

## `routekitai run <script>`

Runs a Python script that uses RouteKitAI (e.g. defines agents and calls `agent.run()` or `runtime.run()`).

```bash
routekitai run path/to/agent_script.py
```

- The script is executed in a way that allows async entrypoints; typically the script uses `asyncio.run(main())` or similar.
- Traces from the run are written to the default trace dir (or the dir set by the script’s runtime/agent).

---

## `routekitai trace <trace_id>`

Prints a trace by ID.

```bash
routekitai trace <trace_id> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--format`, `-f` | Output format: `table` (default), `timeline`, `steps`, `json`, `raw` |
| `--trace-dir`, `-t` | Trace directory (default: `.routekit/traces`) |

---

## `routekitai trace-analyze <trace_id>`

Prints metrics for a trace: timing, token usage, cost (when available).

```bash
routekitai trace-analyze <trace_id> [--trace-dir PATH]
```

---

## `routekitai trace-search [query]`

Searches trace contents.

```bash
routekitai trace-search "query" [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--trace-id` | Limit search to one trace |
| `--event-type` | Filter by event type (e.g. `tool_called`, `model_called`) |
| `--trace-dir` | Trace directory |

---

## `routekitai replay <trace_id>`

Replays a trace with stubbed model and tool responses.

```bash
routekitai replay <trace_id> --agent <agent_name> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--agent` | Agent name to use for replay (required) |
| `--trace-dir` | Trace directory |

---

## `routekitai serve`

Starts the web UI for browsing and viewing traces.

```bash
routekitai serve [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--port`, `-p` | Port (default: 8080) |
| `--host` | Bind address (e.g. `0.0.0.0` for network access) |
| `--trace-dir`, `-t` | Trace directory (default: `.routekit/traces`) |

Requires the **`[ui]`** extra: `pip install "RouteKitAI[ui]"`.

---

## `routekitai test-agent`

Runs sanity checks (e.g. that the package and a minimal agent run correctly).

```bash
routekitai test-agent
```

Useful in CI or after install to verify the environment.

---

## Environment

- **`ROUTEKIT_TRACE_DIR`** — Used by `serve` (and possibly other commands) as the trace directory when `--trace-dir` is not set. Example: `export ROUTEKIT_TRACE_DIR=/var/traces`.

---

## Examples

```bash
# Run an agent script
routekitai run examples/basic.py

# View last run’s trace (use the trace_id printed by the script)
routekitai trace f98eb1b6-6eec-42df-b42a-021dc704620b --format timeline

# Analyze it
routekitai trace-analyze f98eb1b6-6eec-42df-b42a-021dc704620b

# Search all traces for "error"
routekitai trace-search "error"

# Replay
routekitai replay f98eb1b6-6eec-42df-b42a-021dc704620b --agent assistant

# Start trace UI
routekitai serve --port 3000
```
