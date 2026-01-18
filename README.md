# RouteKit

<div align="center">

**A minimal, production-ready framework for building and orchestrating AI agents**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checking: mypy](https://img.shields.io/badge/type%20checking-mypy-blue)](http://mypy-lang.org/)

[Features](#features) • [Quick Start](#quick-start) • [Documentation](#documentation) • [Examples](#examples) • [Contributing](#contributing)

</div>

---

RouteKit is a Python framework for building AI agents with **graph-based orchestration**, **built-in tracing**, and **deterministic replay**. Unlike other frameworks, RouteKit treats observability and testability as first-class features from day one.

## ✨ Features

### 🎯 Core Capabilities

- **Graph-Native Orchestration**: Define agent workflows as explicit graphs with clear control flow
- **Automatic Tracing**: Every execution produces a complete, immutable trace log
- **Deterministic Replay**: Reproduce any agent run exactly for testing and debugging
- **Type-Safe APIs**: Full type hints with mypy compliance
- **Async-First**: Built for modern Python async/await patterns
- **Minimal API**: Just 5 core primitives—no bloat

### 🛡️ Production Features

- **Security Hooks**: PII redaction, tool allow/deny lists, approval gates
- **Memory Support**: Episodic, retrieval, and vector memory backends
- **Policy System**: ReAct, Supervisor, Graph, and custom policies
- **Error Handling**: Comprehensive error types with context
- **CLI Tools**: Run, trace, replay, and test agents from the command line
- **Trace Analysis**: Metrics, timeline visualization, step-by-step debugging, and search

## 🚀 Quick Start

### Installation

```bash
pip install routekit
```

For development with CLI tools:

```bash
pip install "routekit[dev]"
```

### Basic Example

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

### Graph-Based Workflow

```python
import asyncio
from routekit import Agent
from routekit.core.policies import GraphPolicy
from routekit.graphs import Graph, GraphNode, GraphEdge, NodeType
from routekit.providers.local import FakeModel
from routekit.core.tools import EchoTool

# Create models and agents
model1 = FakeModel(name="model1")
model1.add_response("Processing input...")

model2 = FakeModel(name="model2")
model2.add_response("Finalizing result...")

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
    model=model1,
    policy=GraphPolicy(graph=graph)
)

# Run the agent
async def main():
    result = await agent.run("Process this task")
    print(result.output.content)

asyncio.run(main())
```

## 📚 Documentation

- **[Architecture Guide](docs/architecture.md)**: Deep dive into RouteKit's design
- **[Security & Governance](docs/security-and-governance.md)**: Security features and best practices
- **[API Reference](https://routekit.readthedocs.io)**: Complete API documentation (coming soon)

## 🎓 Examples

Check out the [`examples/`](examples/) directory for complete examples:

- **[Basic Agent](examples/hello_routekit.py)**: Simple agent with tools
- **[Graph Orchestration](examples/graph_agent.py)**: Multi-agent workflow
- **[Supervisor Pattern](examples/supervisor_agent.py)**: Supervisor delegating to sub-agents
- **[Evaluation Harness](examples/eval_regression.py)**: Testing agents with datasets

## 🛠️ CLI Commands

RouteKit provides a CLI for common operations:

```bash
# Run an agent script
routekit run agent_script.py

# View a trace (multiple formats available)
routekit trace <trace_id>                    # Table view (default)
routekit trace <trace_id> --format timeline  # Timeline visualization
routekit trace <trace_id> --format steps     # Step-by-step execution
routekit trace <trace_id> --format json      # JSON output
routekit trace <trace_id> --format raw       # Raw JSONL

# Analyze trace metrics
routekit trace-analyze <trace_id>            # Performance metrics, token usage, costs

# Search traces
routekit trace-search "error"                # Search all traces for "error"
routekit trace-search "model" --trace-id abc # Search specific trace
routekit trace-search "tool" --event-type tool_called  # Filter by event type

# Replay a trace
routekit replay <trace_id> --agent my_agent

# Run sanity checks
routekit test-agent
```

## 🏗️ Core Primitives

RouteKit keeps it minimal with 5 core primitives:

1. **Model**: LLM interface abstraction
2. **Message**: Conversation message representation
3. **Tool**: Callable function/tool definition
4. **Agent**: Agent with model and tools
5. **Runtime**: Orchestration and execution engine

## 🧪 Development

### Setup

```bash
# Clone the repository
git clone https://github.com/routekit/routekit.git
cd routekit

# Install with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=routekit --cov-report=html

# Run specific test file
pytest tests/test_runtime.py
```

### Code Quality

```bash
# Type checking
mypy src/

# Linting
ruff check src/

# Format code
ruff format src/
```

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines (coming soon) and:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📋 Requirements

- Python 3.11 or higher
- Pydantic 2.0+

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

RouteKit is inspired by the need for testable, observable AI agent frameworks. Special thanks to the open-source community for their contributions and feedback.

## 🔗 Links

- **GitHub**: [https://github.com/routekit/routekit](https://github.com/routekit/routekit)
- **Documentation**: [https://routekit.readthedocs.io](https://routekit.readthedocs.io) (coming soon)
- **Issues**: [https://github.com/routekit/routekit/issues](https://github.com/routekit/routekit/issues)

---

<div align="center">

Made with ❤️ by the RouteKit contributors

</div>
