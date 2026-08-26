from django.apps import AppConfig


class SchoolConfig(AppConfig):
    name = 'school'

    def ready(self):
        # Auto-seed academic years on startup
        # Only run in main process (not during migrations, tests, etc.)
        import os
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD'):
            try:
                self._seed_academic_years()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to seed academic years: {e}")

        # Start the automatic progression scheduler
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD'):
            try:
                from .scheduler import start_scheduler
                start_scheduler()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to start scheduler: {e}")

    def _seed_academic_years(self):
        """Ensure current academic year exists on startup."""
        from django.utils import timezone
        from .models import AcademicYear
        from django.db import connection

        # Check if table exists
        if AcademicYear._meta.db_table not in connection.introspection.table_names():
            return

        current_year = timezone.now().year
        current_year_str = str(current_year)

        # Ensure all years have is_current=False first
        AcademicYear.objects.all().update(is_current=False)

        # Create or update years around current year
        for year in range(current_year - 1, current_year + 3):
            year_str = str(year)
            AcademicYear.objects.update_or_create(
                name=year_str,
                defaults={
                    'start_date': f'{year}-01-01',
                    'end_date': f'{year}-12-31',
                    'is_current': (year == current_year),
                }
            )
