from django.apps import AppConfig


class SchoolConfig(AppConfig):
    name = 'school'

    def ready(self):
        # Start the automatic progression scheduler
        # Only run in main process (not during migrations, tests, etc.)
        import os
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD'):
            try:
                from .scheduler import start_scheduler
                start_scheduler()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to start scheduler: {e}")
