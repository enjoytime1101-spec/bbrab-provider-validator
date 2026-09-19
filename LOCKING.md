# Dependency locking

The runtime, tests, and repository-local PEP 517 backend use only Python 3.11+ standard-library modules. There is no third-party runtime or build dependency graph to lock. `requirements.lock` records that empty set, while `pyproject.toml` uses `backend-path` to load `build_backend/bbrab_build.py` directly from the source tree.

The release gate creates a fresh venv and runs:

```sh
python -m pip install --no-index --no-build-isolation .
```

`--no-index` proves the install cannot resolve packages from an index. `--no-build-isolation` proves the backend does not rely on an undeclared package already present in an isolated build environment. The installed console command is then used for an offline fixture validation.

For reproducible releases, build in a pinned Python environment and retain the resulting wheel hash as release evidence. Do not add a runtime or build dependency without updating `pyproject.toml`, `requirements.lock`, the security review, and CI.
