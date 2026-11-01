from pathlib import Path
import os
import secrets

from config.paths import APP_DIR, DATA_DIR, STATIC_DIR, TEMPLATES_DIR

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    """Read a boolean environment variable (1/true/yes/on)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Use separate data directory that works both in development and packaged
# In development: project/data
# In packaged: ProgramData/NRZ Student Management (or env var)
APP_DATA_DIR = Path(
    os.environ.get(
        "NRZ_DATA_DIR",
        DATA_DIR
    )
)
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKUP_DIR = APP_DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret_key():
    """Return a secret key that is never hard-coded in the repository.

    Priority:
    1. DJANGO_SECRET_KEY environment variable.
    2. A key generated once and stored beside the database, so sessions and
       password-reset tokens survive restarts.
    3. An ephemeral key if the data directory cannot be written (sessions end
       when the process restarts).
    """
    configured = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if configured:
        return configured

    key_file = APP_DATA_DIR / ".secret_key"
    try:
        if key_file.exists():
            stored = key_file.read_text(encoding="utf-8").strip()
            if stored:
                return stored

        generated = secrets.token_urlsafe(50)
        key_file.write_text(generated, encoding="utf-8")
        try:
            key_file.chmod(0o600)
        except OSError:
            pass
        return generated
    except OSError:
        return secrets.token_urlsafe(50)


SECRET_KEY = _load_secret_key()

# DEBUG stays off unless a developer opts in with DJANGO_DEBUG=1. The packaged
# desktop app and any shared deployment must not expose Django debug pages.
DEBUG = env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost"
    ).split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "corsheaders",

    "school",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "school.middleware.LoginRequiredMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATES_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "school.context_processors.time_override_enabled",
                "school.context_processors.backup_config",
                "school.context_processors.navigation_summary",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": APP_DATA_DIR / "school.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Harare"

USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    STATIC_DIR,
    BASE_DIR / "frontend" / "static",
]

# Serve static files straight from the static directories. This keeps the
# packaged app styled with DEBUG off and without running collectstatic against
# a read-only install directory.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Time Override for Testing
# When True, the application will use a frozen datetime stored in the database
# instead of real time. This is useful for testing semester logic, payment due dates, etc.
# The frozen time is set via the Time Override UI at /time-override/.
# Off by default; opt in with NRZ_ENABLE_TIME_OVERRIDE=1.
ENABLE_TIME_OVERRIDE = env_bool("NRZ_ENABLE_TIME_OVERRIDE", default=False)

# Session / authentication timeout settings
# Auto-logout after 2 hours of inactivity and reset the idle timer on each request.
SESSION_COOKIE_AGE = 7200
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Authentication
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# CORS for Nuxt dev server (port 3000)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"