from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction

from school.models import (
    AcademicYear,
    Semester,
    Program,
    FeeStructure,
    FeeStructureItem,
)


class Command(BaseCommand):
    help = "Generate completed semesters from 2020 up to current year with fee structures"

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-year',
            type=int,
            default=2020,
            help='Starting academic year (default: 2020)'
        )
        parser.add_argument(
            '--end-year',
            type=int,
            default=None,
            help='Ending academic year (default: current year - 1)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing semesters/years in range before generating'
        )

    def handle(self, *args, **options):
        start_year = options['start_year']
        end_year = options['end_year'] or (date.today().year - 1)
        clear = options['clear']

        if start_year > end_year:
            self.stderr.write(self.style.ERROR("Start year must be <= end year"))
            return

        # Get all active programs
        programs = Program.objects.filter(active=True)
        if not programs.exists():
            self.stderr.write(self.style.ERROR("No active programs found. Create programs first."))
            return

        self.stdout.write(f"Generating semesters from {start_year} to {end_year}...")
        self.stdout.write(f"Programs: {[p.name for p in programs]}")

        if clear:
            self.stdout.write("Clearing existing data in range...")
            AcademicYear.objects.filter(name__gte=str(start_year), name__lte=str(end_year)).delete()

        created_years = 0
        created_semesters = 0
        created_fee_structures = 0

        for year_num in range(start_year, end_year + 1):
            year_name = str(year_num)
            
            # Create or get academic year
            academic_year, ay_created = AcademicYear.objects.get_or_create(
                name=year_name,
                defaults={
                    'start_date': date(year_num, 1, 1),
                    'end_date': date(year_num, 12, 31),
                }
            )
            if ay_created:
                created_years += 1
                self.stdout.write(f"  Created academic year: {year_name}")

            # Create 2 semesters per year
            for sem_num in [1, 2]:
                sem_name = f"{year_name} Semester {sem_num}"
                
                # Semester dates: Jan-Jun and Jul-Dec
                if sem_num == 1:
                    start_date = date(year_num, 1, 1)
                    end_date = date(year_num, 6, 30)
                else:
                    start_date = date(year_num, 7, 1)
                    end_date = date(year_num, 12, 31)

                semester, sem_created = Semester.objects.get_or_create(
                    academic_year=academic_year,
                    number=sem_num,
                    defaults={
                        'start_date': start_date,
                        'end_date': end_date,
                    }
                )
                if sem_created:
                    created_semesters += 1
                    self.stdout.write(f"    Created {sem_name}")

                # Create fee structures for all programs and year levels
                for program in programs:
                    for year_level in range(1, program.duration_years + 1):
                        fs, fs_created = FeeStructure.objects.get_or_create(
                            program=program,
                            year_level=year_level,
                            semester=semester,
                        )
                        if fs_created:
                            created_fee_structures += 1
                            # Create default fee items
                            self.create_default_fee_items(fs, program, year_level)
                            self.stdout.write(f"      Created fee structure: {program.name} Year {year_level} for {sem_name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Created {created_years} academic years, "
            f"{created_semesters} semesters, "
            f"{created_fee_structures} fee structures."
        ))

    def create_default_fee_items(self, fee_structure, program, year_level):
        """Create default fee items for a fee structure."""
        base_fees = self.get_base_fees(program, year_level)
        
        for name, amount in base_fees:
            FeeStructureItem.objects.get_or_create(
                fee_structure=fee_structure,
                name=name,
                defaults={
                    'amount': Decimal(str(amount)),
                    'description': f'{name} for {program.code} Year {year_level}',
                }
            )

    def get_base_fees(self, program, year_level):
        """Return default fee items based on program and year level."""
        code = program.code
        
        # Base tuition by year level
        tuition_rates = {
            1: 450,
            2: 500,
            3: 550,
            4: 600,
            5: 650,
            6: 700,
        }
        tuition = tuition_rates.get(year_level, 500)
        
        # Program-specific fees
        if 'ELECT' in code.upper() or 'POWER' in code.upper():
            return [
                ('Tuition', tuition),
                ('Workshop Materials', 80),
                ('Safety Equipment', 40),
                ('Lab Fees', 60),
                ('Examination', 30),
                ('Registration', 20),
            ]
        elif 'FAB' in code.upper() or 'WELD' in code.upper():
            return [
                ('Tuition', tuition),
                ('Workshop Materials', 100),
                ('Welding Consumables', 60),
                ('Safety Equipment', 40),
                ('Lab Fees', 50),
                ('Examination', 30),
                ('Registration', 20),
            ]
        elif 'MILL' in code.upper() or 'MECH' in code.upper():
            return [
                ('Tuition', tuition),
                ('Workshop Materials', 90),
                ('Machine Shop', 70),
                ('Safety Equipment', 40),
                ('Lab Fees', 55),
                ('Examination', 30),
                ('Registration', 20),
            ]
        else:
            return [
                ('Tuition', tuition),
                ('Workshop Materials', 70),
                ('Safety Equipment', 35),
                ('Lab Fees', 50),
                ('Examination', 30),
                ('Registration', 20),
            ]