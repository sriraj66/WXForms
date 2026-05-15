"""
Django settings for backend project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-0mopc%=z$1k1#i@+b@)31imstcuu))cd($+31l%87=d&!xid8t",
)

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Encryption key for Gmail app passwords
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# Application definition
INSTALLED_APPS = [
    # django-unfold MUST be listed before django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "plans",
]

MIDDLEWARE = [
    "backend.logging_utils.RequestLoggingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

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
                "plans.context_processors.credits_context",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
] if not DEBUG else []

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Login/Logout redirects
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Rate limiting (django-ratelimit)
RATELIMIT_ENABLE = True

# Email (default - users configure their own SMTP)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---------------------------------------------------------------------------
# django-unfold (admin theme)
# Vercel-style monochrome palette to match the user dashboard.
# ---------------------------------------------------------------------------
UNFOLD = {
    "SITE_TITLE": "WX Form Admin",
    "SITE_HEADER": "WX Form",
    "SITE_SUBHEADER": "Administration",
    "SITE_URL": "/dashboard/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "THEME": None,  # respect user toggle (light + dark)
    "BORDER_RADIUS": "8px",
    "COLORS": {
        # Neutral monochrome scale (Vercel-like). Values are space-separated RGB.
        "base": {
            "50":  "250 250 250",
            "100": "245 245 245",
            "200": "234 234 234",
            "300": "229 229 229",
            "400": "161 161 161",
            "500": "115 115 115",
            "600": "82 82 82",
            "700": "64 64 64",
            "800": "23 23 23",
            "900": "10 10 10",
            "950": "0 0 0",
        },
        "primary": {
            "50":  "250 250 250",
            "100": "245 245 245",
            "200": "234 234 234",
            "300": "229 229 229",
            "400": "161 161 161",
            "500": "82 82 82",
            "600": "64 64 64",
            "700": "38 38 38",
            "800": "23 23 23",
            "900": "10 10 10",
            "950": "0 0 0",
        },
        "font": {
            "subtle-light":      "var(--color-base-500)",
            "subtle-dark":       "var(--color-base-400)",
            "default-light":     "var(--color-base-700)",
            "default-dark":      "var(--color-base-300)",
            "important-light":   "var(--color-base-900)",
            "important-dark":    "var(--color-base-100)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Plans & Credits",
                "separator": True,
                "items": [
                    {
                        "title": "Credit plans",
                        "icon": "credit_card",
                        "link": "/admin/credits/creditplan/",
                    },
                    {
                        "title": "User balances",
                        "icon": "account_balance_wallet",
                        "link": "/admin/credits/usercreditbalance/",
                    },
                    {
                        "title": "Transactions",
                        "icon": "receipt_long",
                        "link": "/admin/credits/credittransaction/",
                    },
                ],
            },
            {
                "title": "Forms data",
                "separator": True,
                "items": [
                    {"title": "Forms", "icon": "description", "link": "/admin/core/form/"},
                    {"title": "Submissions", "icon": "inbox", "link": "/admin/core/submission/"},
                    {"title": "Email templates", "icon": "mail", "link": "/admin/core/emailtemplate/"},
                    {"title": "Access keys", "icon": "key", "link": "/admin/core/accesskey/"},
                    {"title": "Email logs", "icon": "history", "link": "/admin/core/emaillog/"},
                ],
            },
            {
                "title": "Identity",
                "separator": True,
                "items": [
                    {"title": "Users", "icon": "person", "link": "/admin/auth/user/"},
                    {"title": "Groups", "icon": "group", "link": "/admin/auth/group/"},
                ],
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if not DEBUG else "DEBUG").upper()
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "0"))  # 0 = daily-only rotation
LOG_APP_NAME = os.getenv("LOG_APP_NAME", "wxform")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "backend.logging_utils.RequestIDFilter"},
        "app_name": {"()": "backend.logging_utils.AppNameFilter"},
    },
    "formatters": {
        # time::LEVEL::request_id::app::module.func::message  (no spaces)
        "structured": {
            "format": "%(asctime)s::%(levelname)s::%(request_id)s::%(app)s::%(method)s::%(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        "access": {
            "format": "%(asctime)s::%(levelname)s::%(request_id)s::access::%(message)s ip=%(client_ip)s ua=%(user_agent)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        # Short console formatter: time::LEVEL::id::method::message
        "console": {
            "format": "%(asctime)s::%(levelname)s::%(request_id)s::%(method)s::%(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": LOG_LEVEL,
            "formatter": "console",
            "filters": ["request_id", "app_name"],
        },
        "app_file": {
            "()": "backend.logging_utils.IndexedRotatingFileHandler",
            "level": LOG_LEVEL,
            "formatter": "structured",
            "filters": ["request_id", "app_name"],
            "directory": str(LOG_DIR / "app"),
            "stem": "app",
            "suffix": ".txt",
            "backupCount": LOG_BACKUP_COUNT,
            "maxBytes": LOG_MAX_BYTES,
        },
        "error_file": {
            "()": "backend.logging_utils.IndexedRotatingFileHandler",
            "level": "ERROR",
            "formatter": "structured",
            "filters": ["request_id", "app_name"],
            "directory": str(LOG_DIR / "error"),
            "stem": "error",
            "suffix": ".txt",
            "backupCount": LOG_BACKUP_COUNT,
            "maxBytes": LOG_MAX_BYTES,
        },
        "access_file": {
            "()": "backend.logging_utils.IndexedRotatingFileHandler",
            "level": "INFO",
            "formatter": "access",
            "filters": ["request_id", "app_name"],
            "directory": str(LOG_DIR / "access"),
            "stem": "access",
            "suffix": ".txt",
            "backupCount": LOG_BACKUP_COUNT,
            "maxBytes": LOG_MAX_BYTES,
        },
    },
    "root": {
        "handlers": ["console", "app_file", "error_file"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        # Access log lives in its own file only (not duplicated into app.log).
        "access": {
            "handlers": ["access_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        # Quiet down noisy framework loggers; keep them in app.log at WARNING.
        "django": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["access_file"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console", "app_file", "error_file"], "level": "WARNING", "propagate": False},
        "django.db.backends": {"level": "WARNING", "propagate": True},
        "core": {"level": LOG_LEVEL, "propagate": True},
        "plans": {"level": LOG_LEVEL, "propagate": True},
    },
}
