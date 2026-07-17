"""Minimal Django settings used only for running gando's test suite.

This is intentionally tiny: an in-memory SQLite database and just the apps
gando needs to import cleanly. It is not shipped in the wheel (it lives under
``tests/``, outside ``src/``) and is only referenced by ``DJANGO_SETTINGS_MODULE``
in the pytest configuration.
"""

from pathlib import Path

SECRET_KEY = "gando-test-secret-key-not-for-production"

DEBUG = True

# Required by the ``start*`` scaffolding management commands (they read
# ``settings.BASE_DIR`` at import time to know where to create the generated
# ``repo/`` package). Tests that exercise those commands point Django's
# ``BASE_DIR``-relative app path at a pytest ``tmp_path`` via the app label
# itself, so this only needs to be a valid, existent directory.
BASE_DIR = Path(__file__).resolve().parent

# In-memory SQLite keeps the suite fast and dependency-free.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "simple_history",
    "gando",
    # Carries a single concrete model (``Widget``) built on
    # ``AbstractBaseModel``, so the soft-delete manager/audit-field behavior
    # can be exercised against a real table. Has no migrations, so Django
    # creates its table via the automatic "unmigrated app" syncdb path.
    "tests.testapp",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Exercised by QueryDictSerializer's ``src`` handling and image helpers.
MEDIA_URL = "/media/"

# The default entry ("PBKDF2PasswordHasher") is the "preferred" hasher.
# ``MD5PasswordHasher`` is included only so ``tests/test_hashers.py`` can
# exercise the "encoded with an outdated hasher -> setter called with a
# freshly re-hashed value" upgrade path; never use MD5 in a real project.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
