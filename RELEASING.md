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
sentinel-desktop --help              # entry point from [project.scripts]
```
