# Gando

A standalone, general-purpose Django toolkit (soft-delete abstract models, opinionated admin,
typed fields, a standardized API response envelope) — published to PyPI, consumed by `backend`
as a pinned wheel. Own GitHub repo and owner (`navidsoleymani/gando`), separate from the
`beensi-software` org — this is a shared dependency, not a fourth deployed product stack. See
root `.claude/rules/repo-map.md`.

Root orchestration and the PyPI-publish approval gate (never publish without explicit user
approval, version + full changelog shown first) live in the root `CLAUDE.md`, two levels up.

## Requires Python 3.14+

`ModelClass.id` defaults to `uuid.uuid7`, which only entered the stdlib in 3.14 —
`python_requires` enforces this; `pip install` refuses older interpreters.

**`tox.ini`'s `envlist = py{38,39,310,311,312}` predates this requirement and is stale** — none
of those interpreters can actually import `gando.models`. Don't trust it; run tests directly.

## Commands

- `pytest tests` from the repo root (198 tests as of the last hardening pass)
- `python setup.py check -m -s` — packaging metadata sanity check

## Layout

`src/gando/` (src-layout package): `admin/`, `apis/`, `auth/`, `config/`, `http/`,
`interfaces/`, `management/`, `middlewares/`, `migrations/`, `models/`, `schemas/`,
`serializers/`, `services/`, `utils/`.
