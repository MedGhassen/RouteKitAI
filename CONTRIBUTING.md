# Contributing to RouteKit

Thank you for your interest in contributing to RouteKit! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Documentation](#documentation)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/routekit.git
   cd routekit
   ```
3. **Add the upstream remote**:
   ```bash
   git remote add upstream https://github.com/routekit/routekit.git
   ```

## Development Setup

### Prerequisites

- Python 3.11 or higher
- pip
- git

### Installation

```bash
# Install in development mode with all dependencies
pip install -e ".[dev]"

# Verify installation
python -c "import routekit; print(routekit.__version__)"
```

### Development Tools

The project uses:
- **pytest**: Testing framework
- **mypy**: Type checking
- **ruff**: Linting and formatting
- **pytest-cov**: Coverage reporting

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring
- `test/description` - Test additions/changes

### Commit Messages

Follow conventional commit format:

```
type(scope): subject

body (optional)

footer (optional)
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style (formatting)
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Maintenance tasks

Examples:
```
feat(runtime): add timeout support for tool execution

fix(graphs): prevent infinite loops in graph execution

docs(readme): update installation instructions
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=routekit --cov-report=html

# Run specific test file
pytest tests/test_runtime.py

# Run specific test
pytest tests/test_runtime.py::test_runtime_basic
```

### Writing Tests

- Place tests in the `tests/` directory
- Test files should start with `test_`
- Use descriptive test names
- Follow the AAA pattern: Arrange, Act, Assert
- Use fixtures for common setup

Example:
```python
@pytest.mark.asyncio
async def test_agent_execution():
    # Arrange
    model = FakeModel(name="test")
    agent = Agent(name="test_agent", model=model)
    
    # Act
    result = await agent.run("test prompt")
    
    # Assert
    assert result.output.content is not None
    assert result.trace_id is not None
```

## Code Style

### Formatting

We use `ruff` for formatting:

```bash
# Check formatting
ruff format --check src/ tests/

# Auto-format
ruff format src/ tests/
```

### Linting

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix issues
ruff check --fix src/ tests/
```

### Type Checking

```bash
# Run mypy
mypy src/

# Check specific file
mypy src/routekit/core/runtime.py
```

### Code Style Guidelines

1. **Type hints**: Always use type hints
2. **Docstrings**: Use Google-style docstrings
3. **Line length**: Maximum 100 characters
4. **Imports**: Sort with isort (handled by ruff)
5. **Naming**: Follow PEP 8

## Submitting Changes

### Pull Request Process

1. **Update your fork**:
   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature
   ```

3. **Make your changes** and commit them

4. **Run tests and checks**:
   ```bash
   pytest
   ruff check src/ tests/
   mypy src/
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature
   ```

6. **Open a Pull Request** on GitHub

### Pull Request Checklist

- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] Type checking passes
- [ ] Linting passes
- [ ] Documentation updated (if needed)
- [ ] Commit messages follow conventions
- [ ] Branch is up to date with main

### Review Process

- Maintainers will review your PR
- Address any feedback
- Once approved, your PR will be merged

## Documentation

### Code Documentation

- Use Google-style docstrings
- Document all public APIs
- Include type information
- Add examples for complex functions

### Markdown Documentation

- Update relevant `.md` files
- Follow existing formatting
- Add examples where helpful
- Keep documentation up to date

## Questions?

If you have questions:
- Open an issue on GitHub
- Check existing issues and discussions
- Review the documentation

## Thank You!

Your contributions make RouteKit better for everyone. Thank you for taking the time to contribute!
