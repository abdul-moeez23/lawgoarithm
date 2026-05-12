from .base import *
import os

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.getenv("DB_NAME", "lawyerplatform_test_db"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Use a faster password hasher for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Keep tests deterministic and avoid model downloads from signal-triggered embedding refresh.
AUTO_REFRESH_LAWYER_EMBEDDINGS = False

# Ensure tests don't send real emails
# EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
