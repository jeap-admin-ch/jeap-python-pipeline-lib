# AGENTS.md

Guidance for AI coding agents working **in this repository**. For how to *use* the library in a
pipeline, read [README.md](README.md) and the [docs/](docs/) folder instead.

## Project

`jeap-python-pipeline-lib` is a pure Python library (no CLI, no service) of helpers for jEAP CI/CD
pipelines: AWS ECS deployment/undeployment checks, jEAP Deployment Log service integration, Pact
Broker operations, Message Contract Service operations, business-process test orchestration, and
GitHub / Remedy integrations. It is published to PyPI as `jeap-pipeline` and imported as
`jeap_pipeline`.

## Repository layout

```
pyproject.toml                     # hatchling build; version, deps, metadata (PyPI name: jeap-pipeline)
requirements.txt                   # pinned runtime deps (kept in sync with pyproject [project.dependencies])
src/jeap_pipeline/
  __init__.py                      # the public API — every consumable symbol is re-exported here
  <area>.py                        # one module per area (ecs_deployment_checker, pact_operations, ...)
tests/test_<area>_*.py             # pytest, one or more test files per module
scripts/full_build.py              # deps upgrade + build + pytest + license file
scripts/check_licenses.py          # regenerates THIRD-PARTY-LICENSES.md
docs/                              # published on jeap-admin-ch.github.io
.github/workflows/python-package-build-and-publish.yml   # CI: build + publish to (Test)PyPI
```

## Build & test

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install -e ".[dev]"
python3 -m pytest              # tests
python3 scripts/full_build.py  # deps upgrade + build + tests + THIRD-PARTY-LICENSES.md
```

Python 3.8+. Runtime deps: `boto3`, `requests`.

## Conventions

- **The public API is `src/jeap_pipeline/__init__.py`.** A new consumable function or class must be
  re-exported there; internal helpers are prefixed with `_` and not exported.
- Every public class and function has a docstring (first line is a one-sentence summary — the docs
  pages are derived from these).
- One module per area under `src/jeap_pipeline/`; every module has matching `tests/test_*.py`.
- Pinned dependency versions live in **both** `requirements.txt` and `pyproject.toml` — update both,
  then regenerate `THIRD-PARTY-LICENSES.md` and check license compatibility with Apache-2.0.
- Pages must be valid Markdown/MDX (Docusaurus renders `docs/`): wrap bare `<...>` and `{...}` in
  backticks or code fences.

## Docs

`docs/` is aggregated into the jEAP documentation site — this repo appears under
*App Building Blocks → Tooling & Registries*, with `README.md` as the section landing page and
`docs/getting-started.md` pinned first. Do **not** add a `docs/index.md` (the site would demote it to
`modules.md` and collide with the hand-written one). When changing the public API, update
`docs/modules.md` and, for non-trivial behaviour, the relevant topic page. To preview the rendered
docs, build the site from the `jeap-admin-ch.github.io` repo with
`./preview.sh --local <path-to-this-repo> --no-autodiscover`.

## Versioning

- Version lives in `pyproject.toml`; SemVer / PEP 440.
- Keep `CHANGELOG.md` (Keep a Changelog format) and `publiccode.yml` (`softwareVersion`,
  `releaseDate`) in sync with it.
- Publishing is automatic on push: `main` → PyPI as-is; feature branches → TestPyPI with a
  `.dev<timestamp>` suffix.
- Commit messages: short, prefixed with the JIRA ID from the branch name (e.g. `JEAP-1234 Add ...`);
  no conventional commits.
