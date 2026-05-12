from django.apps import AppConfig


class LawyersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lawyers'

    def ready(self):
        # Register signal handlers for auto-refreshing embeddings.
        import lawyers.signals  # noqa: F401
