from .base import *
import os

# SECURITY WARNING: keep the secret key used in production secret!
# Use environment variables for sensitive data
DEBUG = False

ALLOWED_HOSTS = ['moeez.kashmirtech.dev', 'www.moeez.kashmirtech.dev']

# Database settings for production
# Consider using environment variables for database credentials
DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.getenv("DB_NAME", "lawyerplatform_db"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Session and CSRF settings for HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# For hosting in a subfolder like /lawyerplatformftp/ (if needed)
# FORCE_SCRIPT_NAME = '/lawyerplatformftp/'

# Static and media files in production
# STATIC_ROOT = '/home/kashesvi/moeez.kashmirtech.dev/static'
# MEDIA_ROOT = '/home/kashesvi/moeez.kashmirtech.dev/media'
