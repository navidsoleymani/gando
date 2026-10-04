# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e .
pip install pytest pytest-django
pytest                               # full suite (198+ tests), tests/settings.py is an
                                      # in-memory SQLite Django settings module
pytest tests/path/to_test.py::test_name   # single test

python setup.py check -m -s           # packaging metadata sanity check
python -m build                       # build the sdist/wheel locally
```

**`tox.ini`'s `envlist` predates the Python 3.14 requirement and is stale** — none of those
older interpreters can actually import `gando.models` (see below). Don't trust it; run `pytest`
directly against 3.14.

Requires **Python 3.14+** — `AbstractBaseModel.id` defaults to `uuid.uuid7`, only available in
the 3.14 standard library; this is enforced via `python_requires`, not just documented.

## What this is

Gando is a published PyPI package (`gando`), a Django/DRF toolkit used by `backend` as an
ordinary pinned dependency (see `backend/requirements.txt`). It is **not** a deployed product
surface of its own — changes here only reach production once `backend` bumps its pin. New
behavior and bug fixes are expected to ship with tests (the project went from 0 to 198 tests
specifically by writing tests for previously-uncovered code during a hardening pass — don't
regress that bar).

## Architecture

```
src/gando/      the package: soft-delete abstract models, opinionated admin, typed model
                fields (images, phone, username, password), a standardized API response
                envelope, request/client helpers, and management commands that scaffold a
                clean service-layer app
tests/          pytest-django suite; tests/testapp is a minimal Django app with one concrete
                model built on AbstractBaseModel, used to exercise the soft-delete manager
                against a real table
```

Core conventions the toolkit enforces for any project consuming it: every model built on
`AbstractBaseModel` gets timestamps, a `simple_history` audit trail, an `available` flag, and
soft-delete (`is_deleted`) rather than hard deletion; every API response goes through one
standardized envelope shape rather than ad hoc per-view formats.

**Publishing to PyPI requires explicit user approval** with the exact version and full
changelog shown first — building and preparing a release is fine to do freely, but the upload
step itself is gated. A missing PyPI credential is a stop-and-ask condition, not something to
route around.
