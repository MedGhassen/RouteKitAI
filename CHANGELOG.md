# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffold
- Core primitives: Model, Message, Tool, Agent, Runtime
- Graph-based orchestration with nodes, edges, and state management
- Step-based execution with complete trace capture
- Immutable trace format with event logging
- Deterministic replay engine with stub support
- Policy system: ReAct, FunctionCalling, Graph, Supervisor, PlanExecute
- Memory backends: EpisodicMemory, RetrievalMemory
- Security hooks: PII redaction, tool filtering, approval gates
- CLI tools: run, trace, replay, test-agent commands
- Evaluation harness with dataset support and regression testing
- Multi-agent supervisor pattern with delegation
- Error handling with context and proper exception types
- Type-safe APIs with full mypy compliance
- Async-first design with asyncio support
- Development tooling: ruff, mypy, pytest configuration
- Comprehensive test suite
- Documentation: architecture, security, examples

### Changed
- N/A (initial release)

### Deprecated
- N/A (initial release)

### Removed
- N/A (initial release)

### Fixed
- N/A (initial release)

### Security
- PII redaction for emails, phones, and custom patterns
- Tool allow/deny lists at agent and runtime levels
- Approval gates for high-risk permissions
- Trace security with redaction support

## [0.1.0] - 2024-01-XX

### Added
- Initial public release
- Core framework functionality
- Graph orchestration
- Tracing and replay
- Security features
- CLI tools

---

## Version History

- **0.1.0**: Initial release with core features

## Upcoming Features

See [Architecture Guide](docs/architecture.md#future-directions) for planned features.

## Contributing

See [Contributing Guide](CONTRIBUTING.md) (coming soon) for how to contribute changes.
