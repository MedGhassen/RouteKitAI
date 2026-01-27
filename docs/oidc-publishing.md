# OIDC/Trusted Publishing Setup for PyPI

This document explains how OIDC (OpenID Connect) authentication works for publishing to PyPI using GitHub Actions.

## What is OIDC/Trusted Publishing?

OIDC (OpenID Connect) is a secure authentication method that eliminates the need for long-lived API tokens. PyPI's "Trusted Publishing" feature uses OIDC to authenticate GitHub Actions workflows automatically.

### Benefits

- **No API tokens to manage**: No need to store secrets in GitHub
- **More secure**: Tokens are short-lived and automatically generated
- **Better audit trail**: PyPI logs show which GitHub Actions workflow published each release
- **Automatic rotation**: No need to manually rotate tokens

## Setup Instructions

### 1. Configure Trusted Publisher in PyPI

1. Go to your PyPI project settings:
   - Navigate to: https://pypi.org/manage/project/routekitai/settings/
   - Or: PyPI → Your Project → Manage → Publishing

2. Click "Add a new pending publisher"

3. Fill in the trusted publisher details:
   - **PyPI project name**: `RouteKitAI` (must match exactly)
   - **Owner**: Your GitHub username or organization (e.g., `MedGhassen`)
   - **Repository name**: `RouteKit` (or your actual repository name)
   - **Workflow filename**: `.github/workflows/publish.yml` (must match exactly)
   - **Environment name**: `pypi` (optional, but recommended for protection)

4. Click "Add"

5. The publisher will be in "pending" status until the first successful workflow run

### 2. Verify Workflow Configuration

The workflow must have the correct permissions:

```yaml
permissions:
  id-token: write  # Required for OIDC/Trusted Publishing
  contents: write  # Required for checkout and creating releases
```

The workflow uses the official PyPI action:

```yaml
- name: Publish to PyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    packages-dir: dist/
    print-hash: true
```

### 3. Test the Setup

1. Run the publish workflow manually from GitHub Actions
2. The first run will activate the trusted publisher
3. Subsequent runs will use OIDC authentication automatically

## How It Works

1. **Workflow runs**: GitHub Actions workflow executes
2. **OIDC token request**: The workflow requests an OIDC token from GitHub
3. **Token validation**: PyPI validates the token against the trusted publisher configuration
4. **Authentication**: If valid, PyPI authenticates the workflow
5. **Publish**: The package is uploaded to PyPI

## Troubleshooting

### Publisher Status: Pending

- The publisher stays "pending" until the first successful workflow run
- After the first successful publish, it becomes "active"

### Authentication Fails

Common issues:

1. **Workflow filename mismatch**:
   - Check that the workflow file path matches exactly: `.github/workflows/publish.yml`
   - Case-sensitive!

2. **Repository name mismatch**:
   - Verify the repository owner and name match your GitHub repository
   - Check for typos or case sensitivity

3. **Environment name mismatch**:
   - If you specified an environment in PyPI, ensure the workflow uses the same name
   - The workflow should have: `environment: name: pypi`

4. **Missing permissions**:
   - Ensure `permissions.id-token: write` is set in the workflow
   - This is required for OIDC to work

5. **Project name mismatch**:
   - The PyPI project name must match exactly (case-sensitive)
   - Check in `pyproject.toml`: `name = "RouteKitAI"`

### Check Workflow Logs

If authentication fails, check the workflow logs for:
- OIDC token generation messages
- PyPI authentication errors
- Permission errors

## Security Considerations

### Environment Protection

Using a GitHub Environment (e.g., `pypi`) adds an extra layer of security:

- **Required reviewers**: Require approval before publishing
- **Deployment branches**: Restrict which branches can publish
- **Wait timer**: Add a delay before publishing

To configure:
1. Go to repository Settings → Environments
2. Create/edit the `pypi` environment
3. Configure protection rules as needed

### Workflow Permissions

The workflow uses minimal required permissions:
- `id-token: write` - Only for OIDC authentication
- `contents: write` - Only for creating releases

This follows the principle of least privilege.

## Migration from API Tokens

If you're migrating from API tokens:

1. **Set up trusted publisher** (as described above)
2. **Remove API token secret** from GitHub (optional, but recommended)
3. **Update workflow** to use `pypa/gh-action-pypi-publish` action
4. **Test** with a new version number
5. **Verify** the publisher status changes from "pending" to "active"

## References

- [PyPI Trusted Publishing Documentation](https://docs.pypi.org/trusted-publishers/)
- [GitHub Actions OIDC](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [pypa/gh-action-pypi-publish](https://github.com/pypa/gh-action-pypi-publish)
