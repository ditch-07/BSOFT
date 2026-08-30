from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import connection

from school.models import AcademicYear


class Command(BaseCommand):
    help = 'Seed academic years around the current year.'

    def add_arguments(self, parser):
        parser.add_argument('--back', type=int, default=5, help='Years back from current year')
        parser.add_argument('--forward', type=int, default=10, help='Years forward from current year')

    def handle(self, *args, **options):
        current_year = timezone.now().year
        start = current_year - options['back']
        end = current_year + options['forward']
        created_count = 0

        # Check if table exists
        if AcademicYear._meta.db_table not in connection.introspection.table_names():
            self.stdout.write(self.style.WARNING(
                f'Table {AcademicYear._meta.db_table} does not exist. Run migrations first.'
            ))
            return

        for year in range(start, end + 1):
            obj, created = AcademicYear.objects.get_or_create(
                name=str(year),
                defaults={
                    'start_date': f'{year}-01-01',
                    'end_date': f'{year}-12-31',
                    'is_current': (year == current_year),
                }
            )
            if created:
                created_count += 1

        # Ensure only the current year is marked as current
        AcademicYear.objects.exclude(name=str(current_year)).update(is_current=False)

        self.stdout.write(self.style.SUCCESS(
            f'Created {created_count} academic years. Current year: {current_year}'
        ))