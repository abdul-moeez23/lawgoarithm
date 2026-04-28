from .base import *

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": 'lawyerplatform_db',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET default_storage_engine=InnoDB",
        },
    }
}

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
