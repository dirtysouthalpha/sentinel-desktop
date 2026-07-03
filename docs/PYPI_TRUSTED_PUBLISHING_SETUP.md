# PyPI Trusted Publishing Setup Guide

## Problem
The release pipeline is failing with `403 Forbidden - invalid token` when trying to publish to PyPI using the `PYPI_API_TOKEN` secret.

## Solution: Enable Trusted Publishing (OIDC)

Trusted Publishing is more secure than API tokens and doesn't require managing tokens. It uses OpenID Connect (OIDC) to authenticate GitHub Actions with PyPI.

### Step 1: Configure PyPI Trusted Publishing

1. Go to [PyPI.org](https://pypi.org) and log in
2. Navigate to your project settings: https://pypi.org/manage/project/sentinel-desktop/settings
3. Go to the "Publishing" section
4. Click "Add a new publisher"
5. Enter the following information:
   - **PyPI Project Name**: `sentinel-desktop`
   - **Owner**: `DirtySouthAlpha` (your GitHub username)
   - **Repository name**: `sentinel-desktop`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi` (optional, but recommended for additional security)

### Step 2: Verify GitHub Actions Permissions

The workflow already has the correct permissions:
- `id-token: write` - required for OIDC
- `contents: write` - required for creating releases

### Step 3: Test the Configuration

Once Trusted Publishing is configured on PyPI:

1. Update the version in `core/__init__.py` from `22.0.1` to `22.0.2`
2. Commit the change: `git commit -am "chore(release): bump to 22.0.2"`
3. Create and push the tag:
   ```bash
   git tag -a v22.0.2 -m "v22.0.2 — Trusted Publishing verification"
   git push backup main && git push backup v22.0.2
   ```
4. Monitor the release workflow: https://github.com/DirtySouthAlpha/sentinel-desktop/actions

### Step 4: Cleanup (Optional)

Once Trusted Publishing is working, you can remove the `PYPI_API_TOKEN` secret from GitHub:

1. Go to: https://github.com/DirtySouthAlpha/sentinel-desktop/settings/secrets/actions
2. Delete `PYPI_API_TOKEN`

The workflow will automatically fall back to OIDC if the token is not set.

## Troubleshooting

**Q: The workflow still fails with 403**
- A: Verify that the Trusted Publishing configuration exactly matches your repository details
- A: Make sure the workflow name is exactly `release.yml` (case-sensitive)

**Q: Tests pass but PyPI publish fails**
- A: Check the PyPI project exists and you have admin permissions
- A: Verify the OIDC permissions in the workflow (`id-token: write`)

**Q: GitHub Release succeeds but PyPI fails**
- A: This suggests the issue is specifically with PyPI authentication, not GitHub permissions
- A: Double-check the Trusted Publishing configuration on PyPI

## Benefits of Trusted Publishing

- **No token management**: Tokens expire and need rotation; OIDC doesn't
- **More secure**: Uses short-lived credentials automatically
- **GitHub native**: Integrated directly with GitHub Actions
- **Revoke easily**: Can be removed from PyPI settings without touching GitHub secrets