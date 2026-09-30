"""
Configuración de Alke Wallet.

Base de datos
-------------
* Desarrollo (por defecto): SQLite, sin configuración adicional.
* Producción: PostgreSQL. Se activa con variables de entorno (ver README.md):

      DB_ENGINE=postgres DB_NAME=alke DB_USER=alke DB_PASSWORD=... DB_HOST=localhost DB_PORT=5432

  Requiere el adaptador:  pip install psycopg2-binary
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Seguridad -------------------------------------------------------------
# En producción define DJANGO_SECRET_KEY, DJANGO_DEBUG=False y DJANGO_ALLOWED_HOSTS.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-only-clave-insegura-cambiala-en-produccion"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h]

# --- Aplicaciones ----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",  # sitio de administración (/admin)
    "django.contrib.auth",  # autenticación y usuarios
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",  # CSS / imágenes
    "gestion",  # app principal de Alke Wallet
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # protección CSRF
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "alke_wallet.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "alke_wallet.wsgi.application"

# --- Base de datos ---------------------------------------------------------
if os.environ.get("DB_ENGINE", "sqlite").lower() in ("postgres", "postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",  # usa psycopg2
            "NAME": os.environ.get("DB_NAME", "alke_wallet"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Validación de contraseñas --------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Autenticación (login / logout) ----------------------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "gestion:inicio"
LOGOUT_REDIRECT_URL = "login"

# --- Internacionalización --------------------------------------------------
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True
FORMAT_MODULE_PATH = ["alke_wallet.formats"]  # separador de miles con punto (1.234,56)

# --- Archivos estáticos ----------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # destino de collectstatic (producción)
