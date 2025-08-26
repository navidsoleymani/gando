# Gando — Django toolkit & conventions for Horin Software Group

[![PyPI](https://img.shields.io/pypi/v/gando?label=PyPI\&logo=python)](https://pypi.org/project/gando) <!-- placeholder -->
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
![gando](statics/imgs/gando.svg)

**Gando** is a collection of batteries-included tools, conventions and scaffolding utilities built on top of Django to standardize and accelerate development for the Horin engineering teams.
Named after *Gando* — a small, native crocodile of Sistan and Baluchestan — the project is compact, tough and purpose-built for the local needs of your org.

---

## Quick summary

* **What it is:** A small framework of opinionated building blocks for Django projects: base abstract models, useful model fields (image + validators), admin base classes, API response/exception schemas, request helpers, scaffolding management commands (`startmodel`, `startapi`, `startservice`, `startinterface`, ...), and utilities (image converters/uploaders, string casings, etc).
* **Why:** Aligns Horin internal projects around shared error/response shapes, admin patterns, and developer ergonomics—reduces copy/paste and onboarding time.
* **Status:** Actively developed and extended; features are added on demand.

---

# Table of contents

1. [Key features](#key-features)
2. [Install](#install)
3. [Quickstart (5–10 min)](#quickstart-5-10-min)
4. [Core concepts & architecture](#core-concepts--architecture)
5. [Examples (models, admin, API flow)](#examples-models-admin-api-flow)
6. [Management commands / scaffolding](#management-commands--scaffolding)
7. [Response & request contract](#response--request-contract)
8. [Important notes, gotchas & recommended fixes](#important-notes-gotchas--recommended-fixes)
9. [Development, tests & CI](#development-tests--ci)
10. [Roadmap & contributing](#roadmap--contributing)
11. [License & contact](#license--contact)

---

## Key features

* Opinionated base models: `AbstractBaseModel`, `WhiteAbstractBaseModel`, `AbstractBaseModelFaster` (history-enabled, timestamps, availability flag).
* `AvailableManager` (named `Manager` in current code) that filters `available=1` by default.
* Rich image support: `ImageField` (multi-subfields), `ImageProperty` descriptor, `BlurBase64Field` computed preview.
* Validators & typed model fields: `PhoneNumberField`, `UsernameField`, `PasswordField`, `BooleanNumberField`.
* `BaseModelAdmin` — unified Admin list/filters/readonly behavior and image field rendering.
* API scaffolding: `ResponseSchema`, `RequestSchema`, `Base` / `BaseInterface` for method dispatch and unified response format.
* Scaffolding commands to create repositories, schemas, APIs, interfaces, services and models automatically following the gando conventions.
* Utilities: string casings, image converter (small blur base64), uploaders, and request/response helpers.

---

## Install

```bash
# (recommended: inside virtualenv)
pip install gando
```

or for local editable development:

```bash
git clone https://github.com/navidsoleymani/gando.git
cd gando
pip install -e .
```

Minimum safe `setup.py`/`pyproject` expectations:

* `python_requires='>=3.8'`
* Pin runtime dependencies more conservatively in the future, e.g. `Django>=4.2,<5.0`, `djangorestframework>=3.12`.

---

## Quickstart (minimal)

1. **Add to `INSTALLED_APPS`** in `settings.py`:

```py
INSTALLED_APPS = [
    # ...
    "gando",
    # other apps
]
```

2. **Use an abstract model**:

```py
from gando.models import AbstractBaseModel  # path may vary

class Article(AbstractBaseModel):
    title = models.CharField(max_length=300)
    body = models.TextField()
```

3. **Use the ImageField helper**:

```py
from gando.models import AbstractBaseModel, ImageField

class Product(AbstractBaseModel):
    image = ImageField()
    title = models.CharField(max_length=255)
```

4. **Admin** — reuse the standard admin scaffold:

```py
from django.contrib import admin
from gando.admin import BaseModelAdmin
from .models import Product

@admin.register(Product)
class ProductAdmin(BaseModelAdmin):
    list_display = ['title', 'image']
```

5. **Create scaffolds** (from project root):

```bash
python manage.py startmodel -al your_app_label -mn Product
python manage.py startapi   -al your_app_label -an Product
python manage.py startservice -al your_app_label -sn Product
python manage.py startinterface -al your_app_label -in Product
```

(The flags are: `-al/--applabel`, `-mn/--modelname`, `-an/--apiname`, `-sn/--servicename`, `-in/--interfacename`.)

6. **Migrate** and run:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

---

## Core concepts & architecture

**Design philosophies** (applies across gando):

* **Conventions over configuration** — provide sane defaults (timestamps, availability, admin lists) so teams are consistent.
* **Separation of concerns** — `architectures` contains `apis`, `interfaces`, `services`, `models` and `serializers` and enforces a flow: `API / Interface -> Service -> Repo/Models -> Serializers -> Response`.
* **Unified contracts** — server and client share `RequestSchema` / `ResponseSchema` shapes to avoid divergence.
* **Scaffold-first** — management commands create consistent package/module layout (`repo`, `schemas`, `apis`, `services`).

**Typical request flow**:

1. HTTP request arrives at an API view (generated by scaffolding).
2. Request parsed into `RequestSchema`.
3. `BaseInterface` or `Base` dispatches to a method (`get`, `post`, etc).
4. Interface calls a `Service` that encapsulates business logic.
5. `Service` interacts with `repo` models and returns domain `data`.
6. Response wrapped by `ResponseSchema` and returned.

---

## Examples — Model → Service → API → Response

**Model**:

```py
from gando.models import AbstractBaseModel, ImageField

class Banner(AbstractBaseModel):
    title = models.CharField(max_length=200)
    image = ImageField()
```

**Service (conceptual)**:

```py
from gando.architectures.services import BaseService

class BannerService(BaseService):
    def get_banner(self, banner_id):
        banner = Banner.objects.filter(id=banner_id).first()
        if not banner:
            return {"error": "not_found"}, 404
        return {"banner": BannerSchema.from_orm(banner).dict()}, 200
```

**API / Interface (conceptual)**:

```py
from gando.architectures.apis import BaseAPI  # or BaseInterface

class BannerAPI(BaseAPI):
    def get(self, request, banner_id):
        data, status = BannerService().get_banner(banner_id)
        return ResponseSchema(success=(status==200), status_code=status, data=data)
```

**Client-side Response wrapper** — `BaseResponseSchema` expects the JSON shape used across gando.

---

## Management commands / scaffolding (details)

Gando provides a set of management commands that scaffold folders and files in the target app:

* `startmodel -al <app_label> -mn <modelname>`
  Creates `repo/models/__<ModelName>.py`, updates `repo/models/__init__.py`, app-level `models.py`, `admin.py` entries, `repo/schemas/models/__<modelname>.py`, and URL includes.

* `startapi -al <app_label> -an <apiname>`
  Creates `repo/apis/__<ApiName>.py` with a base API class.

* `startservice -al <app_label> -sn <servicename>`
  Creates service module templates and schema folders.

* `startinterface -al <app_label> -in <interfacename>`
  Creates interface templates under `repo/interfaces`.

**Note:** commands rely on `settings.BASE_DIR` and the app folder structure; run them from the project root.

---

## Response & request contract

Gando standardizes API payloads. A canonical successful response includes:

```json
{
  "success": true,
  "status_code": 200,
  "has_warning": false,
  "exception_status": false,
  "monitor": {},
  "messenger": [],
  "many": false,
  "data": { /* object or list depending on many */ },
  "development_messages": {}
}
```

`ResponseSchema` (server) and `BaseResponseSchema` (client helpers) map to the same shape. Use these everywhere to keep client & server consistent, reduce parsing errors and simplify error handling.

---

## Important notes, gotchas & recommended fixes

I reviewed the code you supplied deeply. Below are concrete findings and recommendations to make Gando safer, more robust and production-friendly.

### 1. `Manager` naming & `available` field

* **Issue:** Generic name `Manager`. It's better to name `AvailableManager` or `ActiveManager`.
* **Recommendation:** Consider using `BooleanField` if `available` is binary; if you anticipate more states, keep integer but rename to `status`/`availability_state` with an Enum.

### 2. `QueryDictSerializer` problems

* `__image_field_name_parser` uses a `equal` variable that is not correctly reset per loop — this creates incorrect prefix matching.
* `__updater` function is fragile and can lose values or produce inconsistent structures for nested merges.
* `__media_url` uses a bare `except:` — this hides unrelated errors.

**Fix suggestions (high level):**

* Replace prefix comparison logic with `str.startswith(prefix)`.
* Implement a robust `deep_merge(a, b)` for dictionaries where `b` values override or are appended appropriately.
* Use `getattr(settings, "MEDIA_URL", "")` instead of try/except.

*Short fixed sketch (extract):*

```py
# safer prefix check
def __image_field_name_parser(self, field_name):
    for img in self.image_fields_name:
        if field_name.startswith(img + "_"):
            return [img, field_name[len(img) + 1:]]
    return [field_name]

# safer media url
from django.conf import settings
@property
def __media_url(self):
    return getattr(settings, 'MEDIA_URL', '')
```

(I can provide a full refactor patch if you want — it will be longer but makes the serializer robust.)

### 3. `BlurBase64Field.pre_save` and remote storage

* **Issue:** `small_blur_base64(_src.file.name)` assumes a local filename and direct filesystem access. If you use remote storages (S3, GCS) this will fail.
* **Recommendation:** Read file content via Django storage API:

```py
from django.core.files.storage import default_storage
if _src:
    try:
        with default_storage.open(_src.name, 'rb') as fh:
            blur = small_blur_base64(fh.read())  # accept bytes in small_blur_base64
            setattr(model_instance, self.attname, blur)
    except Exception:
        # handle/log but don't silence unexpected exceptions
        raise
```

Also consider moving `small_blur_base64` processing off the request thread to a background job (Celery) or compute it once on upload.

### 4. Bare `except:` usage

* There are several `except:` usages that silence all exceptions. Replace with targeted exception types, or at least log and re-raise unexpected ones.

### 5. `BaseModelAdmin` behavior & names

* `list_display` setter uses `id_`, `available_` names which are fine, but keep docstrings and explicit `list_display` examples in README.
* Document `image_fields_name_list` usage in admin to ensure image fieldsets are created.

### 6. Management commands argument handling

* The command handlers expect `kwargs` dict and set `self.app_label = kwargs`. The setter then reads `kwargs.get('applabel')`. This works but is unusual — be explicit in docs that flags are named `-al/--applabel` etc. Also check behavior when flags are missing: the code raises `CommandError` as expected.

### 7. History size & retention

* `HistoricalRecords` on many models can balloon DB size. Add guidance for history pruning or retention policies.

### 8. Packaging / dependencies

* In `setup.py` you currently list unpinned dependencies: prefer minimum versions and ranges for stability, e.g. `Django>=4.2,<5.0`, `djangorestframework>=3.12,<4.0`.

---

## Development, tests & CI

Recommended development stack for the repo:

* **Formatter & linters:** Black, isort, flake8
* **Type checks:** mypy (use strictness progressively)
* **Testing:** pytest + pytest-django
* **Coverage:** coveralls or codecov; aim for > 80% initially.
* **Pre-commit hooks:** pre-commit for formatting and sanity checks.
* **Docs:** Sphinx with `sphinx-autodoc` + READTHEDOCS pipeline
* **CI:** GitHub Actions (lint → tests → packaging → publish on tags)

Example `.github/workflows/ci.yml` stages:

1. Install dependencies (pinned).
2. Run `black --check`, `isort --check`, `flake8`.
3. Run tests with `pytest`.
4. Publish wheel on tag.

---

## Roadmap (suggested)

* **v0.1.x**: Stabilize current APIs, fix QueryDictSerializer, address image storage, add tests & docs.
* **v0.2.x**: Add optional DRF/async adaptors, Celery tasks for image processing, plugin hooks.
* **v1.0.0**: Public stable release with SemVer, complete docs, examples project and migration guides.

Use Semantic Versioning (MAJOR.MINOR.PATCH) and maintain a `CHANGELOG.md` following *Keep a Changelog*.

---

## Contributing

1. Fork the repo and create a feature branch.
2. Run tests locally.
3. Format code with `black` and check `flake8`.
4. Open PR describing the change and tests.
5. Maintainers will review and merge after CI passes.

Please include unit tests for behavior changes and update docs when public APIs change.

---

## License & contact

Gando is released under the **MIT License**. See `LICENSE` for details.
Author: `Hydra` ([navidsoleymani@ymail.com](mailto:navidsoleymani@ymail.com)) — repository: `https://github.com/navidsoleymani/gando.git`.

---

## Appendix — Short patch examples

**1) Safer `__media_url`:**

```py
from django.conf import settings

@property
def __media_url(self):
    return getattr(settings, 'MEDIA_URL', '')
```

**2) Simpler image prefix parser:**

```py
def __image_field_name_parser(self, field_name):
    # return [prefix, suffix] if field_name starts with any image prefix
    for img in self.image_fields_name:
        prefix = f'{img}_'
        if field_name.startswith(prefix):
            return [img, field_name[len(prefix):]]
    return [field_name]
```

**3) Example `deep_merge` (dict merge):**

```py
def deep_merge(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return b
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        elif k in out and isinstance(out[k], list) and isinstance(v, list):
            out[k] = out[k] + v
        else:
            out[k] = v
    return out
```

---

## Final note

You already have a strong, well-structured foundation. With a few fixes (robust serializer merging, safe storage access, explicit exception handling) and solid test coverage, Gando will be a great, reliable toolkit for Horin projects.

If you want, I can now:

* produce a **full, polished `README.md`** file ready to replace the one in your repo (I can drop it into the `canmore` canvas or paste it here), **or**
* prepare a PR-style patch with the exact code changes for the `QueryDictSerializer`, `BlurBase64Field.pre_save`, and other issues I flagged.

Which of those do you want me to do next?
