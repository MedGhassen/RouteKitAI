# Publishing RouteKitAI to PyPI

This document describes how to publish RouteKitAI to PyPI using the GitHub Actions workflow.

## Prerequisites

1. **PyPI Account**: Create an account at https://pypi.org/account/register/

2. **Trusted Publisher Setup (OIDC - Recommended)**:
   - Go to your PyPI project: https://pypi.org/manage/project/routekitai/settings/
   - Navigate to "Publishing" → "Add a new pending publisher"
   - Select "GitHub Actions" as the publisher type
   - Fill in the details:
     - **PyPI project name**: `RouteKitAI`
     - **Owner**: Your GitHub username or organization (e.g., `MedGhassen`)
     - **Repository name**: `RouteKit` (or your repo name)
     - **Workflow filename**: `.github/workflows/publish.yml`
     - **Environment name**: `pypi` (optional, but recommended for protection)
   - Click "Add"
   - **Note**: No API tokens needed! OIDC handles authentication securely.

3. **GitHub Environment Setup** (Optional but Recommended):
   - Go to your repository settings → Environments
   - Click "New environment" and name it `pypi`
   - (Optional) Add environment URL: `https://pypi.org/project/RouteKitAI`
   - Configure protection rules if needed (e.g., required reviewers)
   - **No secrets needed** - OIDC handles authentication automatically

### Alternative: API Token Method (Legacy)

If you prefer to use API tokens instead of OIDC:

1. **API Token**: 
   - Go to https://pypi.org/manage/account/token/
   - Create a new API token with scope: "Entire account" or "Project: routekitai"
   - Copy the token (starts with `pypi-`)

2. **GitHub Environment Setup**: 
   - Go to your repository settings → Environments
   - Click "New environment" and name it `pypi`
   - In the "Secrets" section, add a secret named `PYPI_API_TOKEN` with your PyPI API token
   - **Note**: You'll need to modify the workflow to use `TWINE_USERNAME` and `TWINE_PASSWORD` instead of the OIDC action

## Publishing Process

### Option 1: Using GitHub Actions (Recommended)

1. **Go to Actions tab** in your GitHub repository
2. **Select "Publish to PyPI"** workflow
3. **Click "Run workflow"**
4. **Fill in the form**:
   - **Version**: Enter the version number (e.g., `0.1.0`, `0.1.1`, `1.0.0`)
   - **Skip tests**: Leave unchecked (recommended) to run tests before publishing
5. **Click "Run workflow"** button
6. **Monitor the workflow**:
   - The workflow will run tests (if not skipped)
   - Build the package
   - Publish to PyPI
   - Create a GitHub release

### Option 2: Manual Publishing (Local)

If you prefer to publish manually:

```bash
# 1. Update version in src/routekitai/__init__.py
# Edit __version__ = "0.1.0" to your new version

# 2. Clean previous builds
rm -rf dist/ build/ *.egg-info

# 3. Build the package
python -m build

# 4. Check the package
twine check dist/*

# 5. Upload to TestPyPI (optional, for testing)
twine upload --repository testpypi dist/*

# 6. Upload to PyPI
twine upload dist/*
```

## Version Management

The version is managed in `src/routekitai/__init__.py`:

```python
__version__ = "0.1.0"
```

The GitHub workflow will automatically update this version when you run it.

## Semantic Versioning

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR.MINOR.PATCH** (e.g., `1.0.0`)
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

## Pre-Publishing Checklist

Before publishing, ensure:

- [ ] Version number updated in `src/routekitai/__init__.py`
- [ ] `CHANGELOG.md` updated with release notes
- [ ] All tests pass: `pytest`
- [ ] Linting passes: `ruff check src/ tests/ examples/`
- [ ] Type checking passes: `mypy src/routekitai`
- [ ] README.md is up to date
- [ ] LICENSE file is present
- [ ] Package builds successfully: `python -m build`
- [ ] Package passes checks: `twine check dist/*`

## Post-Publishing

After publishing:

1. **Verify installation**:
   ```bash
   pip install RouteKitAI==<version>
   python -c "import routekitai; print(routekitai.__version__)"
   ```

2. **Check PyPI**: Visit https://pypi.org/project/RouteKitAI/

3. **Update documentation** if needed

4. **Announce the release** on your preferred channels

## Troubleshooting

### Build Errors

If the build fails:
- Check that `MANIFEST.in` includes all necessary files
- Verify `pyproject.toml` is correctly formatted
- Ensure all dependencies are listed

### Upload Errors

If upload fails with OIDC/Trusted Publishing:
- Verify the trusted publisher is configured correctly in PyPI project settings
- Check that the workflow filename matches exactly: `.github/workflows/publish.yml`
- Ensure the repository owner/name matches your GitHub repository
- Verify the environment name is `pypi` (if using environments)
- Check that `permissions.id-token: write` is set in the workflow
- Ensure the workflow is running from the correct branch (usually `main` or `master`)

If using API tokens (legacy):
- Verify `PYPI_API_TOKEN` secret is set correctly in GitHub environment
- Check that the version doesn't already exist on PyPI
- Ensure you have proper permissions on PyPI

### Version Conflicts

If you get a version conflict:
- The version must be unique on PyPI
- Increment the version number
- Check existing versions: https://pypi.org/project/RouteKitAI/#history
