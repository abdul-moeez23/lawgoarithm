from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
# Use environment variables for sensitive data
DEBUG = False

ALLOWED_HOSTS = ['moeez.kashmirtech.dev', 'www.moeez.kashmirtech.dev']

# Database settings for production
# Consider using environment variables for database credentials
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": 'kashesvi_lawyerplatform_db', # Example from your old settings
        'USER': 'kashesvi_root',              # Example from your old settings
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        }
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
