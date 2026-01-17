# RouteKit

**An agent development + orchestration framework**

RouteKit is a minimal, clean framework for building and orchestrating AI agents. Built with Python 3.11+, type hints, and async-first APIs.

## Installation

```bash
pip install routekit
```

For development with CLI tools:

```bash
pip install "routekit[dev]"
```

## Quick Start

### Basic Agent

```python
import asyncio
from routekit import Agent
from routekit.providers.local import FakeModel
from routekit.core.tools import EchoTool

# Create a model
model = FakeModel(name="test")
model.add_response("Hello from RouteKit!")

# Create an agent
agent = Agent(
    name="my_agent",
    model=model,
    tools=[EchoTool()]
)

# Run the agent
async def main():
    result = await agent.run("Hello!")
    print(result.output.content)
    print(f"Trace ID: {result.trace_id}")

asyncio.run(main())
```

### Graph-Based Orchestration

```python
import asyncio
from routekit import Agent
from routekit.core.policies import GraphPolicy
from routekit.graphs import Graph, GraphNode, GraphEdge, NodeType
from routekit.providers.local import FakeModel
from routekit.core.tools import EchoTool

# Create models
model1 = FakeModel(name="model1")
model1.add_response("Processing input...")

model2 = FakeModel(name="model2")
model2.add_response("Finalizing result...")

# Create agents
agent1 = Agent(name="agent1", model=model1, tools=[EchoTool()])
agent2 = Agent(name="agent2", model=model2, tools=[])

# Define a graph: agent1 -> tool -> agent2
graph = Graph(
    name="example_graph",
    entry_node="start",
    exit_node="end",
    nodes=[
        GraphNode(
            id="start",
            type=NodeType.MODEL,
            agent_name="agent1",
            output_mapping={"output": "processed_input"},
        ),
        GraphNode(
            id="echo_tool",
            type=NodeType.TOOL,
            tool_name="echo",
            input_mapping={"processed_input": "message"},
            output_mapping={"result": "echo_result"},
        ),
        GraphNode(
            id="end",
            type=NodeType.MODEL,
            agent_name="agent2",
            input_mapping={"echo_result": "prompt"},
        ),
    ],
    edges=[
        GraphEdge(source="start", target="echo_tool"),
        GraphEdge(source="echo_tool", target="end"),
    ],
)

# Create agent with graph policy
agent = Agent(
    name="graph_agent",
    model=model1,  # Base model (not used in graph execution)
    policy=GraphPolicy(graph=graph)
)

# Run the agent
async def main():
    result = await agent.run("Process this task")
    print(result.output.content)

asyncio.run(main())
```

### With Memory

```python
from routekit import Agent
from routekit.memory.episodic import EpisodicMemory
from routekit.providers.local import FakeModel

# Create agent with episodic memory
memory = EpisodicMemory()
agent = Agent(
    name="agent_with_memory",
    model=FakeModel(name="test"),
    memory=memory
)

# Agent can now use memory for context
result = await agent.run("Remember this: RouteKit is great!")
```

## CLI Commands

RouteKit provides a CLI for common operations:

```bash
# Run an agent script
routekit run agent_script.py

# View a trace
routekit trace <trace_id>

# Replay a trace
routekit replay <trace_id> --agent my_agent

# Run sanity checks
routekit test-agent
```

## MVP Wedge

RouteKit's MVP focuses on three first-class features:

1. **Graph-based Orchestration**: Compose agents into workflows with explicit control flow
2. **Tracing**: Built-in observability for debugging and understanding agent behavior
3. **Replay**: Reproduce and debug agent runs with full trace data

These features are not afterthoughts—they're core to RouteKit's design philosophy.

## Core Primitives

RouteKit keeps it minimal with 5 core primitives:

- **Model**: LLM interface abstraction
- **Message**: Conversation message representation
- **Tool**: Callable function/tool definition
- **Agent**: Agent with model and tools
- **Runtime**: Orchestration and execution engine

## API Examples

### Sync Wrapper (Optional)

```python
from routekit import Agent
from routekit.providers.local import FakeModel

model = FakeModel(name="test")
model.add_response("Hello!")

agent = Agent(name="my_agent", model=model)

# Use sync wrapper
result = agent.run_sync("Hello!")
print(result.output.content)
```

### Policies

```python
from routekit import Agent
from routekit.core.policies import ReActPolicy, SupervisorPolicy, GraphPolicy
from routekit.graphs import Graph

# ReAct policy (default)
agent = Agent(name="agent", model=model, policy=ReActPolicy())

# Supervisor policy
supervisor = SupervisorPolicy(
    sub_agents={"research": research_agent},
    delegation_keywords={"research": ["research", "find"]}
)
agent = Agent(name="supervisor", model=model, policy=supervisor)

# Graph policy
agent = Agent(name="graph_agent", model=model, policy=GraphPolicy(graph=my_graph))
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/
```

## License

MIT
