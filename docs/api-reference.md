# API reference

Overview of the main public APIs in RouteKitAI. For full signatures and docstrings, use the in-editor help or the source under `src/routekitai/`.

---

## Core: `routekitai` (top-level)

| Symbol | Description |
|--------|-------------|
| **Agent** | Agent with model, tools, optional policy and memory. Use `agent.run(prompt)` or `agent.run_stream(prompt)`. |
| **RunResult** | Result of a run: `output` (Message), `trace_id`, `messages`, `final_state`. |
| **Runtime** | Orchestrator: register agents, run with optional policy, replay traces. |
| **Message** | Single message: `role`, `content`, `tool_calls`, `tool_result`, `metadata`. |
| **MessageRole** | Enum: SYSTEM, USER, ASSISTANT, TOOL. |
| **Model** | Abstract LLM interface: `chat(messages, tools=..., stream=...)`. |
| **ModelResponse** | `content`, `tool_calls`, `usage`, `metadata`. |
| **StreamEvent** | Streaming event: `type`, `content`, `tool_calls`, `usage`, `metadata`. |
| **Tool** | Abstract base for tools: `name`, `description`, `input_model`, `output_model`, `run(input)`. |
| **ToolCall** | Model-requested tool call: `id`, `name`, `arguments`. |
| **ToolFilter** | Allow/deny list for tools (agent or runtime hooks). |
| **Usage** | Token/cost info: `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost`. |
| **RouteKitError**, **ModelError**, **ToolError**, **PolicyError**, **RouteKitRuntimeError** | Error types. |

---

## Core: `routekitai.core`

### Agent and runtime

- **Agent** — Same as top-level. Fields: `name`, `model`, `tools`, `policy`, `memory`, `tool_filter`, `trace_dir`.
- **RunResult** — Same as top-level.
- **Runtime** — `agents`, `trace_dir`, `timeout`, `max_concurrency`, `policy_hooks`, etc. Methods: `register_agent()`, `run()`, `replay()`.

### Messages and model

- **Message**, **MessageRole** — As above.
- **Model**, **ModelResponse**, **StreamEvent**, **ToolCall**, **Usage** — As above.

### Tools

- **Tool** — Base class. Subclass and implement `run(input) -> output`. Optional: `input_model`, `output_model`, `permissions`, `timeout`, `redact_fields`.
- **ToolPermission** — Enum: NETWORK, FILESYSTEM, DATABASE, NONE.
- **EchoTool**, **HttpGetTool**, **FileReadTool** — Built-in tools in `routekitai.core.tools`.

### Policies

- **Policy** — Abstract: `plan(state) -> list[Action]`, `reflect(state, observation) -> state`.
- **Action** — Base for model/tool/parallel/final actions.
- **ModelAction**, **ToolAction**, **Parallel**, **Final** — Action types.
- **ReActPolicy** — Reasoning + acting loop (default). Config: `max_iterations`.
- **FunctionCallingPolicy** — Strict function-calling.
- **GraphPolicy** — Runs a `Graph`; requires a Runtime with registered agents.
- **SupervisorPolicy** — Delegates to other agents.
- **PlanExecutePolicy** — Plan then execute.
- **PolicyAdapter** — Adapts policy interface for the runtime.

### Hooks (security and governance)

- **PolicyHooks** — Container: `pii_redaction`, `tool_filter`, `approval_gate`.
- **PIIRedactionHook** — Redact emails, phones, custom patterns.
- **ToolFilter** — `allowed_tools` / `denied_tools`.
- **ApprovalGate** — Require approval for certain permissions; `approval_callback(tool_name, tool_args) -> bool`.

---

## Graphs: `routekitai.graphs`

| Symbol | Description |
|--------|-------------|
| **Graph** | Workflow: `name`, `nodes`, `edges`, `entry_node`, `exit_node`, `state_schema`, `config`. |
| **GraphNode** | Node: `id`, `type` (NodeType), `agent_name` / `tool_name` / `subgraph_name` / `condition`, `input_mapping`, `output_mapping`. |
| **GraphEdge** | Edge: `source`, `target`, optional `condition`. |
| **NodeType** | Enum: MODEL, TOOL, SUBGRAPH, CONDITION. |
| **GraphExecutor** | Executes a graph (used internally by GraphPolicy). |

---

## Memory: `routekitai.memory`

| Symbol | Description |
|--------|-------------|
| **Memory** | Abstract interface (from `routekitai.core.memory`). |
| **WorkingMemory** | In-memory context for a single run. |
| **EpisodicMemory** | SQLite-backed episode storage. |
| **RetrievalMemory** | TF-IDF or substring search. |
| **VectorMemory** | Vector similarity search (in `routekitai.memory.vector`). |
| **KVMemory** | Key-value store (in `routekitai.memory.kv`). |

---

## Evaluations: `routekitai.evals`

| Symbol | Description |
|--------|-------------|
| **Dataset** | Evaluation dataset (inputs and expected outputs). |
| **EvalRunner** | Runs an agent over a dataset and computes metrics. |
| **ExactMatchMetric**, **ContainsMetric**, **RegexMetric** | Built-in metrics. |

---

## Providers: `routekitai.providers`

| Symbol | Description |
|--------|-------------|
| **FakeModel** | Local model with preloaded responses (no API key). |
| **OpenAIChatModel** | OpenAI chat API. |
| **AnthropicChatModel** | Anthropic API (if installed). |
| **AzureOpenAIChatModel** | Azure OpenAI (if installed). |

---

## Observability: `routekitai.observability`

- **Trace**, **TraceEvent** — Trace representation.
- **JSONLExporter** — Writes traces to `.routekit/traces/<trace_id>.jsonl`.
- **Analyzer** — Trace analysis (used by CLI `trace-analyze`).
- **OtelExporter** — OpenTelemetry export (optional).

---

## Sandbox: `routekitai.sandbox`

- **FilesystemSandbox** — Restrict filesystem access.
- **NetworkSandbox** — Restrict network access.
- **PermissionManager** — Manages tool permissions (used by runtime).

---

## Version

```python
import routekitai
print(routekitai.__version__)
```
