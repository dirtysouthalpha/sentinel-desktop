# Releasing

`sentinel-desktop` is a **Python** package published to **PyPI**, plus a GitHub Release with
the built artifacts. Publishing is automated by `.github/workflows/release.yml`, which runs
on every `vX.Y.Z` tag: **test → build (sdist + wheel) → publish to PyPI → GitHub Release**.

## One-time setup

The workflow uses PyPI **Trusted Publishing** (OIDC) — no API token is stored. Configure it once:

1. Create the project on PyPI (first release may need a manual `twine upload`, see below).
2. PyPI → your project → **Settings → Publishing → Add a trusted publisher**:
   - Owner: `dirtysouthalpha`
   - Repository: `sentinel-desktop`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. In GitHub: **Settings → Environments → New environment → `pypi`** (the workflow's
   `publish-pypi` job runs in this environment).

*(Alternative: skip trusted publishing and add a `PYPI_API_TOKEN` secret, then add
`with: { password: ${{ secrets.PYPI_API_TOKEN }} }` to the `pypa/gh-action-pypi-publish` step.)*

## Cut a release

The version is dynamic — `pyproject.toml` reads it from `core.__version__`.

```bash
# 1. Bump the version
#    edit core/__init__.py  ->  __version__ = "X.Y.Z"

# 2. Commit and tag
git commit -am "Release vX.Y.Z"
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

Pushing the tag triggers `release.yml`. Watch it under the **Actions** tab; it publishes to
PyPI and creates the GitHub Release with `dist/*` attached.

## Manual publish (fallback / first release)

```bash
python -m pip install --upgrade build twine
python -m build                      # -> dist/*.whl + dist/*.tar.gz
twine upload dist/*                  # prompts for PyPI token (use a token, username __token__)
```

## Verify

```bash
pip install sentinel-desktop
sentinel-desktop --help              # GUI/API entry point
sentinel-mcp-server                  # MCP server (stdio transport, default)
SENTINEL_MCP_TRANSPORT=http sentinel-mcp-server   # HTTP transport (Tailscale fleet)
```

### v18 — dependency extras

As of v18, `pyproject.toml` is the single source of truth and `requirements.txt`
is a thin `-e .[all]` pointer. Headline features ship as extras so a bare
`pip install sentinel-desktop` stays light:

```bash
pip install "sentinel-desktop[all]"              # every subsystem feature
pip install "sentinel-desktop[web,netops]"       # browser + SSH only
pip install "sentinel-desktop[mcp]"              # MCP server entry point
# Individual extras: [web] [netops] [net] [voice] [mfa] [ocr] [windows] [tray]
```

### First-ever tag (v18)

v18.0.0 was the **first** `vX.Y.Z` git tag ever pushed — the release pipeline
(`release.yml` → PyPI Trusted Publishing → GitHub Release) had never run end-to-end
before. If a future release is the first on a new machine, run the manual publish
fallback above once, then confirm Trusted Publishing is configured (see
"One-time setup").

