"""Minimal Django settings used only for running gando's test suite.

This is intentionally tiny: an in-memory SQLite database and just the apps
gando needs to import cleanly. It is not shipped in the wheel (it lives under
``tests/``, outside ``src/``) and is only referenced by ``DJANGO_SETTINGS_MODULE``
in the pytest configuration.
"""

SECRET_KEY = "gando-test-secret-key-not-for-production"

DEBUG = True

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

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
