from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = []

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'django_htmx',
    'django_celery_beat',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

LOCAL_APPS = [
   'core',
   'companies',
   'access',
   'resources',
   'work',
   'subcontracts',
   'tracking',
   'planning',
   'analytics',
   'notifications',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'work.middleware.AssignmentFlowGuardMiddleware',
]

ROOT_URLCONF = 'ac_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.active_site',
            ],
        },
    },
]

WSGI_APPLICATION = 'ac_system.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'access.User'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

# ─────────────────────────────────────────────────────────────────────────────
# CELERY
# ─────────────────────────────────────────────────────────────────────────────

# Redis como broker y backend de resultados
# En desarrollo usa Redis local: redis://localhost:6379/0
# En produccion configurar via variable de entorno
CELERY_BROKER_URL         = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND     = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')

CELERY_ACCEPT_CONTENT     = ['json']
CELERY_TASK_SERIALIZER    = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE           = 'America/Santiago'
CELERY_ENABLE_UTC         = True

# Beat — scheduler de tareas periodicas
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Reintentos automaticos ante fallo de conexion al broker
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'auto-close-sessions': {
        'task': 'work.auto_close_sessions',
        'schedule': 15 * 60,  # cada 15 minutos
    },
}

# ── Allauth ───────────────────────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

ACCOUNT_LOGIN_METHODS         = {'email'}
ACCOUNT_SIGNUP_FIELDS         = ['email*']
ACCOUNT_EMAIL_VERIFICATION    = 'none'
ACCOUNT_SIGNUP_DISABLED       = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD    = 'email'
ACCOUNT_ADAPTER               = 'access.adapters.NoSignupAccountAdapter'

SOCIALACCOUNT_AUTO_SIGNUP     = False
SOCIALACCOUNT_EMAIL_REQUIRED  = True
SOCIALACCOUNT_LOGIN_ON_GET    = True
SOCIALACCOUNT_ADAPTER         = 'access.adapters.NoNewUsersAdapter'

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    }
}

LOGIN_REDIRECT_URL  = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

# ── Tiempo de sesión ───────────────────────────────────────────────────────────────

SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 horas
SESSION_SAVE_EVERY_REQUEST = True