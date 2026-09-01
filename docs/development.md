# Development

Working on the library itself (not consuming it — for that see [Getting started](getting-started.md)).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

`requirements.txt` holds the runtime dependencies with pinned versions; the `dev` optional-dependency
group in `pyproject.toml` adds `build`, `pytest`, `twine` and `pip-licenses`.

## Test

```bash
python3 -m pytest
```

Every module in `src/jeap_pipeline/` has a matching `tests/test_*.py`.

## Build

```bash
python3 scripts/full_build.py
```

This upgrades the dependencies, runs `python -m build` (producing an sdist and a wheel in `dist/`),
runs the tests, and regenerates `THIRD-PARTY-LICENSES.md`. To regenerate only the license file:

```bash
python3 scripts/check_licenses.py --target-python .venv/bin/python
```

## Adding a module

- Add `src/jeap_pipeline/<name>.py` with docstrings on every public class and function.
- Re-export the public symbols from `src/jeap_pipeline/__init__.py` (the package's public API is
  what is importable from the top level).
- Add `tests/test_<name>.py`.
- If the module has non-trivial behaviour, add a topic page under `docs/` and link it from
  [modules.md](modules.md); otherwise just add a row to the module catalog there.
- Add a `CHANGELOG.md` entry.

## Adding a dependency

- Add it (pinned) to `requirements.txt` **and** to `pyproject.toml` (`[project].dependencies`, or
  `[project.optional-dependencies].dev` for dev-only tools).
- Check its license is compatible with Apache-2.0 and regenerate `THIRD-PARTY-LICENSES.md`.

## Versioning and publishing

- The version lives in `pyproject.toml` and must follow SemVer / PEP 440. Keep `CHANGELOG.md` and
  `publiccode.yml` in sync.
- Publishing is automated by `.github/workflows/python-package-build-and-publish.yml` on every push:
  - **`main`** — the version is published as-is to PyPI.
  - **feature branches** — a `.dev<timestamp>` suffix is appended and the artifact goes to TestPyPI.

## Related

- [Getting started](getting-started.md)
- [Modules](modules.md)
