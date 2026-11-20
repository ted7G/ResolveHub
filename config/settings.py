"""
Django settings for ResolveHub.

Every environment-specific value is read from environment variables. In local
development they can live in a `.env` file next to manage.py (see
`.env.example`). Missing required values fail loudly at startup instead of
falling back to something that only works on a laptop.
"""

from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Real environment variables always win over values in .env.
environ.Env.read_env(BASE_DIR / ".env")


# --- Core -------------------------------------------------------------------

DEBUG = env.bool("DEBUG", default=False)
SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"] if DEBUG else [])
# The site is served over HTTPS on each allowed host, so those origins are
# trusted for form posts unless a different list is given explicitly.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[f"https://{host}" for host in ALLOWED_HOSTS if host and host[0] not in ".*"],
)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.github",
    "accounts",
    "tickets",
    "assistant",
]

MIDDLEWARE = [
    # First, so container health probes skip the host and HTTPS checks.
    "config.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last, so it can turn a lockout raised during login into a 403 page.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.sign_in_options",
            ],
        },
    },
]


# --- Database ---------------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("DATABASE_URL must point to a PostgreSQL database.")

# Reuse connections between requests, but check them before use so a
# connection the provider dropped while idle doesn't surface as a 500.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Bound how long a request can wait on the database, so an unreachable
# server or a runaway query fails with an error instead of holding a thread.
_db_options = DATABASES["default"].setdefault("OPTIONS", {})
_db_options.setdefault("connect_timeout", env.int("DB_CONNECT_TIMEOUT", default=10))
_db_options.setdefault(
    "options", f"-c statement_timeout={env.int('DB_STATEMENT_TIMEOUT_MS', default=30000)}"
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Cache ------------------------------------------------------------------
#
# Shared between worker processes because the assistant's rate limits live
# here. Requires `manage.py createcachetable` (run by the build script).

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}


# --- File storage -----------------------------------------------------------
#
# Uploads go to S3-compatible object storage: Cloudflare R2 in production,
# though AWS S3, Backblaze B2 or a self-hosted Garage/MinIO work the same way.
# "local" and "memory" exist only for development and the test suite, and
# are refused unless DEBUG is on, so production can never quietly write
# uploads to the container's ephemeral disk.

STORAGE_BACKEND = env("STORAGE_BACKEND", default="s3")

if STORAGE_BACKEND == "s3":
    _default_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET_NAME"),
            "endpoint_url": env("S3_ENDPOINT_URL"),
            "access_key": env("S3_ACCESS_KEY_ID"),
            "secret_key": env("S3_SECRET_ACCESS_KEY"),
            "region_name": env("S3_REGION", default="auto"),
            "signature_version": "s3v4",
            # Self-hosted servers (Garage, MinIO) need "path" unless they are set
            # up for bucket subdomains.
            "addressing_style": env("S3_ADDRESSING_STYLE", default=None),
            # The bucket stays private; files are served through short-lived
            # signed URLs generated for users who can already see the ticket.
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 600,
            "file_overwrite": False,
        },
    }
elif STORAGE_BACKEND in ("local", "memory"):
    if not DEBUG:
        raise ImproperlyConfigured(
            f"STORAGE_BACKEND={STORAGE_BACKEND!r} is only allowed with DEBUG=True. "
            "Configure S3-compatible storage for production."
        )
    _default_storage = {
        "BACKEND": (
            "django.core.files.storage.FileSystemStorage"
            if STORAGE_BACKEND == "local"
            else "django.core.files.storage.InMemoryStorage"
        )
    }
else:
    raise ImproperlyConfigured(f"Unknown STORAGE_BACKEND {STORAGE_BACKEND!r}.")

STORAGES = {
    "default": _default_storage,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Attachments are capped at 5 MB (see tickets.validators). Keeping the
# in-memory threshold slightly above that means accepted uploads are streamed
# straight to object storage without touching a temp file on local disk.
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024


# --- Auth and sessions ------------------------------------------------------

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "admin:login"

# Brute-force protection for the login form (django-axes). Five failures for
# the same username from the same IP lock that pair out for 15 minutes;
# keying on the pair means an attacker can't lock a real user out everywhere.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/lockout.html"
# Behind the platform's proxy the client address arrives in X-Forwarded-For.
# Without this every visitor would share the proxy's IP, and per-IP
# lockouts would turn into per-username lockouts.
AXES_CLIENT_IP_CALLABLE = "accounts.client_ip.client_ip"
# Proxies between the internet and the app that append to X-Forwarded-For:
# 1 for Coolify's Traefik; 2 if a CDN such as Cloudflare sits in front.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=1)

# Sign in with GitHub (django-allauth), enabled only when credentials are set.
# GitHub is an extra way into an existing staff account, never a way to get
# one: a signed-in user links their GitHub account first, sign-up is closed,
# and roles stay on the Django user. Accounts are not matched by email,
# which would let a GitHub account claim a staff login it was never linked to.
GITHUB_CLIENT_ID = env("GITHUB_CLIENT_ID", default="")
GITHUB_CLIENT_SECRET = env("GITHUB_CLIENT_SECRET", default="")
GITHUB_LOGIN_ENABLED = bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)

SOCIALACCOUNT_ONLY = True  # no allauth password, sign-up or reset pages
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_ADAPTER = "accounts.adapters.ClosedSignupAccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.LinkedAccountsOnlyAdapter"
SOCIALACCOUNT_FORMS = {"disconnect": "accounts.forms.UnlinkGitHubForm"}
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {
    "github": {
        "SCOPE": ["read:user"],
        "APPS": (
            [{"client_id": GITHUB_CLIENT_ID, "secret": GITHUB_CLIENT_SECRET}]
            if GITHUB_LOGIN_ENABLED
            else []
        ),
    }
}
LOGIN_REDIRECT_URL = "/admin/"

SESSION_COOKIE_AGE = 60 * 60 * 8  # one working day
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True


# --- HTTPS and security headers ---------------------------------------------

# The platform's proxy (Traefik under Coolify) terminates TLS
# and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0 if DEBUG else 60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# HSTS preload is a long-term commitment that binds the whole parent domain,
# which a single app shouldn't make on its own, so it's deliberately left off.
SILENCED_SYSTEM_CHECKS = ["security.W021"]


# --- Internationalization ---------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Logging ----------------------------------------------------------------
# Everything goes to stdout so the hosting platform's log viewer has it.

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        # Server errors only: permission denials and 404s are normal use of the
        # admin and would bury real failures. Failed logins are still logged by axes.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}


# --- Form assistant ---------------------------------------------------------
#
# Optional. Without an API key the admin works normally and the help widget
# explains that the assistant isn't set up. OPENAI_BASE_URL points the client
# at any OpenAI-compatible provider (e.g. Groq or Gemini) instead.

OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-4o-mini")
ASSISTANT_TIMEOUT_SECONDS = env.float("ASSISTANT_TIMEOUT_SECONDS", default=20.0)
ASSISTANT_REQUESTS_PER_MINUTE = env.int("ASSISTANT_REQUESTS_PER_MINUTE", default=6)
ASSISTANT_REQUESTS_PER_DAY = env.int("ASSISTANT_REQUESTS_PER_DAY", default=100)
