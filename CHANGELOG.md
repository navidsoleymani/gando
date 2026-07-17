# Changelog

All notable changes to **gando** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.1] - 2026-07-17

A follow-up hardening pass: a full read-through of the entire source tree
(all of `models/`, `apis/`, `admin/`, `services/`, `parsers/`, `http/`,
`interfaces/`, the `start*` management commands, and every validator/utility
module) looking specifically for logic that ~150+ backend files depend on
but that had zero test coverage. Every bug below was found *because* writing
a real test for the surrounding code immediately reproduced it -- none were
found by inspection alone. No public class/function was renamed or removed;
this is a backward-compatible bug-fix release.

### Fixed

- **`startapi`/`startservice`/`startinterface` generated a stub that could
  never import** (`gando/management/commands/{startapi,startservice,
  startinterface}.py`). Each wrote `from gando.architectures.{apis,services,
  interfaces} import Base*` into the generated file -- a module path from the
  pre-2.x nested package layout that no longer exists in the current flat
  layout. Every developer running one of these three scaffolding commands got
  an immediately broken (`ModuleNotFoundError`-on-import) stub. Fixed to
  `from gando.apis import BaseAPI`, `from gando.services import
  BaseService`, and `from gando.interfaces import BaseInterface`
  respectively.
- **Every `start*` scaffolding command crashed the first time it was run
  against a brand-new package** (`startmodel.py`, `startapi.py`,
  `startservice.py`, `startinterface.py`, all four carried an identical
  private `__new_line` helper). It indexed `lines[-1]` on a freshly-read
  `__init__.py` unconditionally; a brand-new `__init__.py` (created moments
  earlier by `package_maker`'s `Path(...).touch()`) is empty, so `lines[-1]`
  raised `IndexError` immediately. Fixed to treat an empty file the same as
  "no trailing newline yet, and nothing to separate from".
- **`HEXColor` validator accepted malformed values with junk before/after a
  valid-looking hex color** (`gando/utils/validators/color/base.py`), e.g.
  `"#FF0000<script>"` or `"javascript:#FF0000"` both passed. The pattern
  wrote the equivalent of `^(#(...))|(...)$` -- because `|` has the lowest
  precedence in a regex, that parsed as "starts with `#`+6/8 hex chars
  (anything may follow)" **or** "ends with 6/8 hex chars (anything may
  precede)", not "the whole string is one or the other". Fixed to
  `^#?(...)$`, anchoring both alternatives to the full string.
- **`BaseGetterService` (a documented "service-layer building block" key
  feature) crashed on construction, unconditionally** (`gando/services/
  getter.py`). `__filters` chained `.extract()` onto the result of
  `model_dump()` -- a plain `dict` has no such method -- so simply
  instantiating *any* concrete subclass raised `AttributeError` in
  `__init__`, regardless of whether `get_from_db()` was ever called. Fixed to
  `model_dump(exclude_none=True)`, matching the evident intent: drop
  filter fields the caller did not supply (which default to `None`) so they
  do not turn into an accidental `.filter(some_field=None)` constraint.
- **`GenericAPIView.adding_user_id_to_request_data` silently did nothing
  whenever `request.data` started out as an empty dict**
  (`gando/utils/http/request/base.py`, shared by `_request_adder`/
  `_request_remover`/`_request_changer`). The guard was `hasattr(request,
  'data') and request.data`, which treats an empty-but-present dict as
  falsy -- exactly the common case of a client sending an empty body and
  relying on the server to inject `user`. Since this runs automatically on
  every `POST`/`PUT`/`PATCH` dispatched through `GenericAPIView`, an empty
  request body meant the authenticated user's id was never written into
  `request.data`. Fixed to only treat a missing attribute or an explicit
  `None` as "no data".
- **`BaseAPI._exception_handler_messages` dropped its parent dict key when
  the nested value was a list** (`gando/apis/base.py`), so the very common
  DRF validation shape `{"field": ["This field is required."]}` recorded the
  developer error message under the bare leaf code (`"required"`) instead of
  `"field__required"`, losing which field the message was about. Fixed by
  threading `base_key` through the list-recursion branch too.
- **`verbose_name()` (used internally by every `ImageField` sub-field)
  raised `IndexError`/crashed on an empty string or a field name ending in an
  underscore** (`gando/models/fields/base.py`) -- a trailing underscore is a
  common Python convention for avoiding a builtin-name clash (e.g. `type_`).
  Rewritten with a safe tokenizing implementation that produces identical
  output for every normal snake_case input.
- **`gando.utils.json.encoders.Encoder` silently serialized unsupported types
  as JSON `null`** instead of raising the standard `TypeError: Object of type
  X is not JSON serializable`. `JSONEncoder.default`'s return value is used
  *as the serialized substitute*, not a "can I handle this?" predicate; the
  previous implementation returned `None` (the implicit return of a function
  with no `else`) for anything that wasn't a `date`/`datetime`, which hid
  real bugs in callers (a `Decimal`, a `set`, a model instance, ... quietly
  turning into `null`). Now delegates to `super().default(obj)` for anything
  else, restoring the standard contract.
- **Packaging metadata (`python_requires`/classifiers) claimed support for
  Python 3.10-3.13**, but `gando.models.abstract_model_class.ModelClass.id`
  uses `default=uuid.uuid7`, which the standard library only gained in Python
  3.14 -- `import gando.models` (and therefore nearly the whole package)
  raises `AttributeError: module 'uuid' has no attribute 'uuid7'` on any
  older interpreter. Corrected `python_requires` to `>=3.14` and the
  classifiers accordingly.

### Added

- **Substantially expanded test suite: 22 -> 198 tests.** New files target
  the sensitive/critical logic identified by a full source-tree read-through
  that had no prior coverage: `tests/test_api_base.py` (`BaseAPI`'s response
  envelope/success logic/exception-message flattening, `GenericAPIView`'s
  `check_validate_user` and `adding_user_id_to_request_data` security
  helpers, `DestroyAPIView`'s soft/hard delete), `tests/test_validators.py`
  (every `gando.utils.validators.*` type plus the `Validator` dispatcher),
  `tests/test_hashers.py` (password hash round-trip, wrong-password
  rejection, hasher-upgrade path), `tests/test_abstract_base_model.py`
  (`AbstractBaseModel`'s soft-delete manager and audit fields against a real
  table, via a new `tests/testapp` Django app), `tests/test_getter_service.py`
  (the `BaseGetterService` crash fix above), `tests/test_request_updater.py`
  (the empty-`request.data` fix above), `tests/test_management_commands.py`
  (both scaffolding-command fixes above), `tests/test_deep_dict.py`,
  `tests/test_json_encoder.py`, `tests/test_casing.py`, and
  `tests/test_verbose_name.py`.
- `tests/settings.py` gained `BASE_DIR` (needed by the `start*` commands) and
  an explicit `PASSWORD_HASHERS` list (needed to exercise the hasher-upgrade
  path in `tests/test_hashers.py`).
- `tests/testapp/` -- a minimal concrete Django app/model
  (`tests.testapp.models.Widget`, built on `AbstractBaseModel`) used only by
  the test suite, so the soft-delete manager and UUID primary key can be
  exercised against a real (in-memory SQLite) table.

### Changed

- `setup.py`: `python_requires` `>=3.10` -> `>=3.14` and classifiers updated
  (see Fixed).

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
