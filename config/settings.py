from pathlib import Path
import os

from config.paths import APP_DIR, DATA_DIR, STATIC_DIR, TEMPLATES_DIR

BASE_DIR = Path(__file__).resolve().parent.parent

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

SECRET_KEY = "nrz-local-development-key"
DEBUG =True

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "school",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

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

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Harare"

USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    STATIC_DIR,
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Time Override for Testing
# When True, the application will use a frozen datetime stored in the database
# instead of real time. This is useful for testing semester logic, payment due dates, etc.
# The frozen time is set via the Time Override UI at /time-override/
ENABLE_TIME_OVERRIDE = True  # Set to False in production

# Authentication
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"