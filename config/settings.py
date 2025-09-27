# config/settings.py
from pathlib import Path
import environ
from datetime import timedelta
import cloudinary

# -----------------------
# BASE DIR
# -----------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------
# ENV SETUP
# -----------------------
env = environ.Env(
    DEBUG=(bool, False)
)
environ.Env.read_env(BASE_DIR / ".env")  

# -----------------------
# SECRET & DEBUG
# -----------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://ppp7rljm-8000.inc1.devtunnels.ms/",
    "http://localhost:3143",
    "http://10.10.13.2:3143",
    "https://tourapi.dailo.app",
]

# -----------------------
# CORS SETTINGS
# -----------------------
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    'http://10.10.13.2:3000',
    "https://ppp7rljm-8000.inc1.devtunnels.ms",
    "http://localhost:3143",
    "http://10.10.13.2:3143",
    "https://tourist-ai-dashboard.vercel.app",


]

CORS_ALLOW_CREDENTIALS = True
# -----------------------
# INSTALLED APPS
# -----------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",

    # Your apps
    "apps.users",
    "apps.scans",
    "apps.payments",

]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# -----------------------
# MIDDLEWARE
# -----------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
]

# -----------------------
# URLS
# -----------------------
ROOT_URLCONF = "config.urls"

# -----------------------
# TEMPLATES
# -----------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# -----------------------
# WSGI
# -----------------------
WSGI_APPLICATION = "config.wsgi.application"

# -----------------------
# DATABASE
# -----------------------
DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
        "OPTIONS": {
            "options": "-c search_path=tour"  # 👈 sets schema to 'tour'
        },
    }
}

# -----------------------
# AUTH
# -----------------------
AUTH_USER_MODEL = "users.User"

# -----------------------
# PASSWORD VALIDATION
# -----------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------
# INTERNATIONALIZATION
# -----------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# -----------------------
# STATIC & MEDIA
# -----------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

MEDIA_URL = env("MEDIA_URL", default="/media/")
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=BASE_DIR / "media"))

# -----------------------
# REST FRAMEWORK
# -----------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# -----------------------
# SIMPLE JWT
# -----------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=env.int("ACCESS_TOKEN_LIFETIME_DAYS", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# -----------------------
# AUTO FIELD
# -----------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------
# OPENAI API KEY
# -----------------------
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")

# -----------------------
# EMAIL CONFIGURATION
# -----------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

# -----------------------------
# Stripe API Keys
# -----------------------------
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")

# -----------------------------
# Booster Product Prices (HKD)
# -----------------------------
BOOSTER_PRODUCT_ID = env("BOOSTER_PRODUCT_ID")

BOOST_1H_PRICE_ID = env("BOOST_1H_PRICE_ID")
BOOST_6H_PRICE_ID = env("BOOST_6H_PRICE_ID")
BOOST_12H_PRICE_ID = env("BOOST_12H_PRICE_ID")
BOOST_24H_PRICE_ID = env("BOOST_24H_PRICE_ID")
BOOST_2D_PRICE_ID = env("BOOST_2D_PRICE_ID")
BOOST_5D_PRICE_ID = env("BOOST_5D_PRICE_ID")
BOOST_7D_PRICE_ID = env("BOOST_7D_PRICE_ID")
BOOST_10D_PRICE_ID = env("BOOST_10D_PRICE_ID")
BOOST_LIFETIME_PRICE_ID = env("BOOST_LIFETIME_PRICE_ID")

# -----------------------------
# Cloudinary Config
# -----------------------------
CLOUDINARY = {
    "cloud_name": env("CLOUDINARY_CLOUD_NAME"),
    "api_key": env("CLOUDINARY_API_KEY"),
    "api_secret": env("CLOUDINARY_API_SECRET"),
}

cloudinary.config(
    cloud_name=CLOUDINARY["cloud_name"],
    api_key=CLOUDINARY["api_key"],
    api_secret=CLOUDINARY["api_secret"]
)

