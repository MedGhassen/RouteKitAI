# RouteKit Architecture

## The Wedge: Graph-Native Orchestration + Tracing + Replay

RouteKit's MVP focuses on **deterministic, testable agent runs** through three first-class features:

1. **Graph-native orchestration**: Agents compose into explicit workflows with clear control flow
2. **Tracing**: Every execution produces an immutable event log
3. **Replay**: Deterministic re-execution using trace data and stubs

These aren't add-ons—they're core to RouteKit's design from day one.

## Why This Is Different

Most agent frameworks treat orchestration, observability, and testing as separate concerns added later. RouteKit inverts this:

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

RouteKit executes agents in discrete **steps**. Each step:
- Takes a message and context
- Produces a message and metadata
- Records all inputs/outputs to the trace
- Can trigger tool calls, sub-agent calls, or control flow decisions

Steps are the atomic unit of execution and tracing.

### Traces as Immutable Event Logs

Every runtime execution produces a **trace**: an immutable, append-only log of events:

- Step start/end events
- Message events (input/output)
- Tool call events (request/response)
- Control flow events (branching, loops)
- Error events

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

## MVP Scope

### Included

- **Core primitives**: Model, Message, Tool, Agent, Runtime
- **Graph orchestration**: Define agent workflows as directed graphs
- **Step-based execution**: Discrete execution steps with full trace capture
- **Trace format**: Immutable event log structure
- **Replay engine**: Deterministic re-execution with stubs
- **Basic tooling**: Save/load traces, stub generation

### Excluded (Post-MVP)

- **Distributed execution**: Multi-machine orchestration
- **Streaming traces**: Real-time trace streaming/aggregation
- **Trace analysis**: Advanced querying, visualization, metrics
- **Production observability**: Integration with monitoring systems
- **Advanced graph features**: Dynamic graphs, conditional branching beyond basics
- **Model providers**: Built-in integrations (use adapters)
- **UI/dashboards**: Trace visualization tools

## Non-Goals for MVP

1. **General-purpose workflow engine**: RouteKit is for agents, not arbitrary workflows
2. **Model provider abstraction**: Focus on orchestration, not model integration
3. **Production monitoring**: Observability tools come later
4. **Multi-tenancy**: Single-tenant execution model
5. **Performance optimization**: Correctness and testability first, speed later

## Design Principles

1. **Minimal core**: 5 primitives max, no bloat
2. **Type-safe**: Full type hints, mypy-clean
3. **Async-first**: Built for async I/O from the ground up
4. **Testable**: Every feature must support deterministic testing
5. **Traceable**: Every execution produces a complete trace
