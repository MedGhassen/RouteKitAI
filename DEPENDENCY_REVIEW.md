# Dependency Management Review

## Summary

This document reviews the dependency management setup for RouteKitAI and identifies issues and recommendations.

## Issues Found

### 1. **Missing Core Dependencies**

#### `httpx` - CRITICAL
- **Status**: Currently in `dev` optional dependencies
- **Usage**: Used in core provider modules:
  - `src/routekitai/providers/anthropic.py`
  - `src/routekitai/providers/openai.py`
  - `src/routekitai/providers/azure_openai.py`
- **Impact**: Core functionality (model providers) will fail without this dependency
- **Recommendation**: Move to core `dependencies` array

### 2. **Missing Optional Dependencies**

#### `nest-asyncio`
- **Status**: Not listed in any dependency group
- **Usage**: Used in `src/routekitai/core/agent.py` (line 251) for `run_sync()` method
- **Impact**: `run_sync()` will fail with ImportError if not installed
- **Recommendation**: Add to `optional` dependencies group

### 3. **CI/CD Workflow Dependencies**

#### Security Tools
- **Status**: Installed in CI but not in `dev` dependencies
- **Tools**: `safety`, `bandit`
- **Usage**: Used in `.github/workflows/ci.yml` (line 108)
- **Impact**: Inconsistent dependency management
- **Recommendation**: Add to `dev` optional dependencies

### 4. **Version Constraints**

#### `numpy`
- **Status**: No upper bound specified (`numpy>=1.24.0`)
- **Impact**: Could break with future major version changes
- **Recommendation**: Add upper bound (e.g., `numpy>=1.24.0,<3.0.0`)

#### `ruff`
- **Status**: Very loose constraint (`ruff>=0.1.0`)
- **Impact**: Could break with breaking changes
- **Recommendation**: Use more specific version or add upper bound

### 5. **Dependency Organization**

#### Provider Dependencies
- **Status**: Model providers require `httpx` but it's not clearly documented
- **Recommendation**: Consider creating a `providers` optional dependency group

#### OpenTelemetry
- **Status**: OTEL exporter exists but no OTEL dependencies listed
- **Usage**: `src/routekitai/observability/exporters/otel.py` uses `httpx` for now
- **Recommendation**: If OTEL SDK is needed later, add to optional dependencies

## Recommendations

### Immediate Fixes

1. **Move `httpx` to core dependencies**
   ```toml
   dependencies = [
       "pydantic>=2.0.0,<3.0.0",
       "numpy>=1.24.0,<3.0.0",
       "httpx>=0.24.0",
   ]
   ```

2. **Add `nest-asyncio` to optional dependencies**
   ```toml
   optional = [
       "sentence-transformers>=2.2.0",
       "faiss-cpu>=1.7.4",
       "openai>=1.0.0",
       "nest-asyncio>=1.5.0",
   ]
   ```

3. **Add security tools to dev dependencies**
   ```toml
   dev = [
       # ... existing ...
       "safety>=2.0.0",
       "bandit>=1.7.0",
   ]
   ```

### Future Improvements

1. **Create provider dependency group**
   ```toml
   providers = [
       "httpx>=0.24.0",
       "openai>=1.0.0",
   ]
   ```

2. **Tighten version constraints** where appropriate

3. **Document dependency groups** in README

## Current Dependency Structure

### Core Dependencies
- `pydantic>=2.0.0,<3.0.0` ✓
- `numpy>=1.24.0` ⚠️ (needs upper bound)

### Optional Dependencies

#### `dev`
- Testing: `pytest`, `pytest-asyncio`, `pytest-cov`
- Linting: `ruff`, `mypy`
- CLI tools: `httpx`, `rich`, `typer` ⚠️ (httpx should be core)
- Missing: `safety`, `bandit`

#### `ui`
- `fastapi>=0.104.0` ✓
- `uvicorn[standard]>=0.24.0` ✓

#### `optional`
- `sentence-transformers>=2.2.0` ✓
- `faiss-cpu>=1.7.4` ✓
- `openai>=1.0.0` ✓
- Missing: `nest-asyncio`

## Testing Recommendations

1. Test installation with minimal dependencies: `pip install RouteKitAI`
2. Test with optional groups: `pip install RouteKitAI[optional,ui]`
3. Verify all imports work correctly with proper dependency groups
4. Add dependency checks to CI/CD pipeline
