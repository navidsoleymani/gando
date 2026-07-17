# Changelog

All notable changes to **gando** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-07-17

First release produced under maintained changelog + test discipline. This is a
hardening pass: it fixes the long-standing bugs documented in the README's
"Important notes, gotchas & recommended fixes" section (re-verified against the
real current source), removes every bare `except`, adds a test suite, and
corrects the packaging metadata. No public class/function was renamed or
removed.

### Fixed

- **`QueryDictSerializer` image-prefix matching**
  (`gando/models/serializers/base.py`). `__image_field_name_parser` used a
  single `equal` flag initialised once *outside* the loop: after the first
  non-matching prefix set it to `False` it stayed `False`, so a later, genuinely
  matching image prefix was skipped. The raw character comparison also ignored
  the separating underscore, raising `IndexError` for names that merely shared
  leading characters with a prefix (e.g. `imagery` vs. prefix `image`). Both are
  fixed with an explicit `str.startswith(f"{prefix}_")` check.
- **`QueryDictSerializer` nested-dict merge** (`__updater`). The previous nested
  `for`/`for` loop produced order-dependent, lossy results when merging dicts
  with more than one key (a later key could overwrite an already-merged value).
  Replaced with a non-mutating recursive deep merge.
- **`QueryDictSerializer.__media_url`** now reads
  `getattr(settings, "MEDIA_URL", "")` instead of wrapping the access in a bare
  `except`, so unrelated import/configuration errors are no longer swallowed.
- **`BlurBase64Field.pre_save` on remote storage**
  (`gando/models/fields/base.py`). It previously computed the preview from
  `_src.file.name` — a storage-relative name that PIL treats as a local
  filesystem path — which silently produced no preview on S3/GCS/any non-local
  backend. It now reads the image through the `FieldFile`/storage API
  (`.open("rb")`), rewinds the file for the subsequent `ImageField` save, and
  degrades gracefully to `None` on a missing/unreadable file.
- **Bare `except` blocks removed across the codebase.** `models/base.py`
  (`current_user_id`/`current_user_agent_info` → `(AttributeError,
  ObjectDoesNotExist)`), `utils/http/response/base.py` (`page_size_inf` parse →
  `(TypeError, ValueError)`), `utils/parsers/images/base.py` and the four
  `start*` management commands now use narrowed/`Exception` handlers with
  explanatory comments. Behaviour is preserved; only over-broad interpreter-level
  catches (`KeyboardInterrupt`/`SystemExit`) are no longer suppressed.

### Added

- **Remote-storage-friendly `small_blur_base64`**
  (`gando/utils/converters/images/base.py`). In addition to a filesystem path,
  it now also accepts raw `bytes`/`bytearray` and open binary file-like objects,
  which is what enables `BlurBase64Field` to work with remote storages. Returns
  `None` (instead of a bare `return`) on undecodable input. Fully backward
  compatible — existing path-based calls are unchanged.
- **Test suite** (`tests/`) using `pytest` + `pytest-django`, with a minimal
  `tests/settings.py` (in-memory SQLite) and pytest configuration in
  `setup.cfg`. 22 tests covering the serializer fixes, the blur-preview
  converter, `BlurBase64Field.pre_save` (including the remote-storage and
  missing-file paths), the request/user helpers, and `inf_response` parsing.
  This is the project's first automated test coverage.
- Full docstrings on every module/function/method touched in this pass.

### Changed

- **Packaging metadata corrected** (`setup.py`):
  - `python_requires` raised from `>=3.8` to `>=3.10`. The code already used
    PEP 604 unions (`X | Y`) at runtime (e.g. in the `start*` management
    commands and `schemas/base.py`), so it could not import on 3.8/3.9; the old
    value was inaccurate rather than a supported floor. No real platform support
    is dropped.
  - `install_requires` given conservative **lower** bounds (no upper caps, to
    keep working with modern Django 6.x / DRF stacks). Notably `pydantic>=2.0`
    is now a hard requirement: the code calls the v2-only `BaseModel.model_dump()`
    API, which does not exist in pydantic 1.x, so an unpinned install could
    previously resolve to a broken environment.
  - Classifiers updated to advertise Python 3.10–3.13 and Django 4.2/5.0/5.1.

### Notes

- **Source/version reconciliation.** Before this release the git repository's
  tracked source had drifted from what was actually built and shipped: the
  source tree carried `__version__ = '1.0.4'` in an older `architectures/`-nested
  layout, while the wheel vendored by downstream consumers was `gando-2.2.1`
  built from a newer flat layout (`gando/models/`, `gando/apis/`,
  `gando/services/`, `gando/serializers/`, `gando/interfaces/`,
  `gando/middlewares/`, ...). The repository source has been reconciled to the
  real, byte-for-byte 2.2.1 that consumers run; this `2.3.0` release continues
  from that true baseline.
- The README gotcha about the generic manager name (`Manager`) was already
  resolved in the 2.2.1 baseline — managers are now named
  `AbstractBaseModelManager`, `ModelClassManager`, `SoftDeleteManager`, etc. —
  so no change was needed there.

## [2.2.1] - prior baseline (historical, summarized)

The `2.x` line refactored gando from the earlier `architectures/`-nested
package layout into a flat, import-friendly layout
(`gando.models`, `gando.apis`, `gando.services`, `gando.serializers`,
`gando.admin.models`, `gando.interfaces`, `gando.middlewares`, ...), on which
downstream consumers depend. It also introduced soft-delete abstract models
(`AbstractBaseModel` built on `SoftDeleteBaseModelClass` + `ModelClass`),
`simple_history` integration, the response/exception schema stack, request
helpers, and the `start{model,api,service,interface}` scaffolding commands.
Detailed per-release history for `< 2.3.0` was not maintained at the time and is
summarized here rather than reconstructed commit-by-commit.
