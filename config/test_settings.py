"""
Settings for the test suite.

Identical to the real settings except for a few overrides that make tests
fast and keep them away from external services. DATABASE_URL still has to
point at PostgreSQL; pytest-django creates a separate test database there.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")
# In-memory file storage is only accepted with DEBUG on. Django's test runner
# switches DEBUG back off while the tests actually run.
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("STORAGE_BACKEND", "memory")

from .settings import *  # noqa: E402, F403

# Hashing cost is irrelevant in tests and argon2 makes user-heavy tests slow.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# The manifest storage needs collectstatic to have run first.
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
# Nothing is collected in tests; without this WhiteNoise warns about the
# missing STATIC_ROOT directory on every request.
STATIC_ROOT = None

# Tests never call a real model provider; the ones that need a key set it.
OPENAI_API_KEY = ""
