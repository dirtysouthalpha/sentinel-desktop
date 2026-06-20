# Pytest Cleanup

If tests fail with `FileNotFoundError: .pytest_tmp`, the temporary directory may have gotten into a bad state. Clean it:

```bash
rm -rf .pytest_tmp && mkdir .pytest_tmp
```

Then re-run tests. Pytest is configured with `--basetemp=.pytest_tmp` in `pyproject.toml`.
