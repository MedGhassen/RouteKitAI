# RouteKitAI Architecture

## Overview

RouteKitAI is designed around a simple but powerful philosophy: **graph-native orchestration, tracing-first observability, and replay-built-in testing**. These aren't add-ons—they're core to RouteKitAI's design from day one.

## The Wedge: Three First-Class Features

RouteKitAI's MVP focuses on **deterministic, testable agent runs** through three integrated features:

1. **Graph-native orchestration**: Agents compose into explicit workflows with clear control flow
2. **Tracing**: Every execution produces an immutable event log
3. **Replay**: Deterministic re-execution using trace data and stubs

### Why This Matters

Most agent frameworks treat orchestration, observability, and testing as separate concerns added later. RouteKitAI inverts this:

- **Graph-native**: Workflows are graphs, not linear scripts. Control flow is explicit and inspectable.
- **Tracing-first**: Every run produces a complete trace. No opt-in, no sampling—always on.
- **Replay-built-in**: Testing isn't an afterthought. Replay uses the same runtime with stubs, ensuring production and test behavior match.

This enables:
- **Deterministic testing**: Replay any run with exact inputs/outputs
- **Debugging**: Inspect full execution history, not just logs
- **Reproducibility**: Re-run failed executions to diagnose issues
- **Confidence**: Test agent behavior before deploying

## Execution Model

### Step-Based Runtime

RouteKitAI executes agents in discrete **steps**. Each step:
- Takes a message and context
- Produces a message and metadata
- Records all inputs/outputs to the trace
- Can trigger tool calls, sub-agent calls, or control flow decisions

Steps are the atomic unit of execution and tracing. This granularity enables:
- Precise replay matching
- Detailed observability
- Fine-grained error handling
- Parallel execution control

### Traces as Immutable Event Logs

Every runtime execution produces a **trace**: an immutable, append-only log of events:

- `step_started`: Step execution begins
- `step_completed`: Step execution finishes
- `model_called`: LLM API call made
- `tool_called`: Tool execution request
- `tool_result`: Tool execution result
- `error`: Error occurred during execution
- `run_started`: Agent run begins
- `run_completed`: Agent run finishes

Traces are:
- **Immutable**: Once written, never modified
- **Complete**: Every event is recorded
- **Structured**: Events are typed and queryable
- **Portable**: Can be saved, loaded, and replayed

### Replay as Deterministic Re-Execution

Replay uses the same runtime with **stubs**:

1. Load a trace from a previous run
2. Replace external calls (LLM, tools, APIs) with stubs that return recorded values
3. Re-execute using the trace's event sequence
4. Verify outputs match the original trace

This ensures:
- **Determinism**: Same inputs → same outputs
- **Speed**: No real API calls during replay
- **Reliability**: Test against real production traces
- **Debugging**: Step through execution with full context

## Core Components

### 1. Model Interface

The `Model` abstract base class provides a unified interface for LLM providers:

```python
class Model(ABC):
    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        stream: bool = False,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        ...
```

This abstraction allows RouteKitAI to work with any LLM provider (OpenAI, Anthropic, local models, etc.) without coupling to specific APIs.

### 2. Message System

Messages are the currency of agent communication:

```python
class Message(BaseModel):
    role: MessageRole  # SYSTEM, USER, ASSISTANT, TOOL
    content: str
    tool_calls: list[dict[str, Any]] | None
    tool_result: dict[str, Any] | None
    metadata: dict[str, Any]
```

Messages flow through the system, carrying context and enabling multi-turn conversations.

### 3. Tool System

Tools are callable functions that agents can invoke:

```python
class Tool(BaseModel, ABC):
    name: str
    description: str
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    
    @abstractmethod
    async def run(self, input: BaseModel) -> BaseModel:
        ...
```

Tools use Pydantic models for input/output validation, ensuring type safety and clear contracts.

### 4. Agent

An agent combines a model, tools, and optional memory:

```python
class Agent(BaseModel):
    name: str
    model: Model
    tools: list[Tool]
    memory: Memory | None
    policy: Policy | None
```

Agents are stateless—all state is managed by the Runtime.

### 5. Runtime

The Runtime orchestrates agent execution:

```python
class Runtime(BaseModel):
    agents: dict[str, Agent]
    trace_dir: Path | None
    policy_hooks: PolicyHooks | None
    max_concurrency: int
    timeout: float | None
    ...
```

The Runtime:
- Manages agent registration
- Executes steps according to policies
- Records traces
- Handles errors and timeouts
- Supports replay

## Graph Orchestration

### Graph Structure

Graphs define workflows as directed graphs:

```python
class Graph(BaseModel):
    name: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    entry_node: str
    exit_node: str | None
    state_schema: dict[str, Any] | None
```

### Node Types

- **MODEL**: Execute an agent/model call
- **TOOL**: Execute a tool
- **SUBGRAPH**: Execute a nested graph
- **CONDITION**: Conditional branching based on state

### State Management

Graphs maintain state that flows between nodes:

- **Input mapping**: Maps graph state to node inputs
- **Output mapping**: Maps node outputs to graph state
- **State schema**: Optional JSON schema for validation

### Execution Flow

1. Start at `entry_node`
2. Execute current node with mapped inputs
3. Update graph state with node outputs
4. Determine next node(s) based on edges and conditions
5. Repeat until `exit_node` or no more edges

## Policy System

Policies determine what actions an agent takes:

```python
class Policy(ABC):
    async def plan(self, state: dict[str, Any]) -> list[Action]:
        ...
    
    async def reflect(self, state: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
        ...
```

### Built-in Policies

- **ReActPolicy**: Reasoning + Acting loop (default)
- **FunctionCallingPolicy**: Strict function calling mode
- **GraphPolicy**: Execute a graph workflow
- **SupervisorPolicy**: Multi-agent coordination
- **PlanExecutePolicy**: Plan then execute pattern

### Action Types

- **ModelAction**: Call the model
- **ToolAction**: Execute a tool
- **Parallel**: Execute multiple actions in parallel
- **Final**: Terminate with output

## Memory System

RouteKitAI supports multiple memory backends:

- **EpisodicMemory**: SQLite-backed episode storage
- **RetrievalMemory**: TF-IDF or substring search
- **VectorMemory**: Vector similarity search (planned)
- **KVMemory**: Key-value storage (planned)

Memory is accessed through the `Memory` abstract interface, allowing agents to retain context across runs.

## Security & Governance

### Policy Hooks

Policy hooks intercept execution at key points:

- **PII Redaction**: Automatically redact sensitive data
- **Tool Filtering**: Allow/deny lists for tools
- **Approval Gates**: Require approval for high-risk operations

### Sandboxing

Sandboxing provides isolation for tool execution:

- **FilesystemSandbox**: Control file system access
- **NetworkSandbox**: Control network access
- **Permissions**: Fine-grained permission system

## MVP Scope

### Included

- Core primitives: Model, Message, Tool, Agent, Runtime
- Graph orchestration: Define agent workflows as directed graphs
- Step-based execution: Discrete execution steps with full trace capture
- Trace format: Immutable event log structure
- Replay engine: Deterministic re-execution with stubs
- Basic tooling: Save/load traces, stub generation
- Memory backends: Episodic and retrieval memory
- Security hooks: PII redaction, tool filtering, approval gates
- CLI tools: Run, trace, replay, test commands

### Excluded (Post-MVP)

- Distributed execution: Multi-machine orchestration
- Streaming traces: Real-time trace streaming/aggregation
- Trace analysis: Advanced querying, visualization, metrics
- Production observability: Integration with monitoring systems
- Advanced graph features: Dynamic graphs, conditional branching beyond basics
- Model providers: Built-in integrations (use adapters)
- UI/dashboards: Trace visualization tools

## Design Principles

1. **Minimal core**: 5 primitives max, no bloat
2. **Type-safe**: Full type hints, mypy-clean
3. **Async-first**: Built for async I/O from the ground up
4. **Testable**: Every feature must support deterministic testing
5. **Traceable**: Every execution produces a complete trace
6. **Composable**: Build complex workflows from simple primitives
7. **Extensible**: Easy to add new models, tools, policies, memory backends

## Performance Considerations

RouteKitAI prioritizes correctness and testability over raw performance:

- **Correctness first**: Deterministic behavior is more important than speed
- **Testability**: Replay enables fast, reliable tests
- **Observability**: Complete traces enable debugging and optimization
- **Async I/O**: Non-blocking operations for concurrent execution

Performance optimizations can be added later without breaking the core design.

## Future Directions

- **Distributed execution**: Scale across multiple machines
- **Advanced graph features**: Dynamic graphs, parallel node execution
- **Trace analysis**: Query, visualize, and analyze traces
- **Production observability**: Integrate with monitoring systems
- **Model provider integrations**: Built-in support for major LLM providers
- **UI/dashboards**: Visual trace inspection and graph editing
