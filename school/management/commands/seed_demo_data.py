"""
Seed believable demo data for the school fees system.

Place this file at:

    school/management/commands/seed_demo_data.py

(make sure ``school/management/__init__.py`` and
``school/management/commands/__init__.py`` exist), then run:

    python manage.py seed_demo_data

What it builds
--------------
Three academic years ending with the current one (calendar-year academic
years, two semesters each, matching how AcademicYear/Semester are modelled):

* Programs (trades) with realistic durations and categories
* Fee structures for every program / year level / semester, with yearly fee
  increases and a mix of fee lines (Tuition, Levy, Practical Materials,
  Examination Fee, Registration Fee)
* Students: a main January intake, a small July intake, and "legacy" cohorts
  (imported into the first seeded year at year levels 2 and 3, the way the
  bulk-import screen would do it)
* Enrollments + charges created exactly like the views do (every semester of
  the academic year is enrolled and charged up front; year level advances at
  the yearly bulk-progression run; finished students become COMPLETED)
* Withdrawals (which clear unpaid/future charges, as cancel_unpaid_future_charges
  does), deferrals (some of whom return), status logs
* Payments with realistic behaviour: paid in full, instalments, late payers,
  partial payers, non-payers, and arrears settled in later semesters; cash /
  EcoCash / bank mix that shifts over time; weekdays only, no Zimbabwe public
  holidays; receipt numbers allocated by the model in date order
* Audit log entries in the same shape the views write them
* created_at / enrolled_at / timestamp fields are back-dated to match events

Nothing is written outside the school app's tables except a few staff users
(registrar, bursar, cashier1, cashier2) used to attribute audit entries.

Options
-------
--years N     number of academic years to seed, ending with the current one
              (default 3)
--intake N    approximate January intake across all programs (default 260)
--seed N      random seed, same seed gives the same data (default 42)
--flush       delete ALL existing school data first (asks for confirmation
              unless --noinput is given)
--password P  password for the demo staff users (default: unusable password)
"""

import random
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from school.models import (
    AcademicYear,
    AuditLog,
    Enrollment,
    FeeStructure,
    FeeStructureItem,
    Payment,
    Program,
    Semester,
    Student,
    StudentCharge,
    StudentStatusLog,
    TimeOverride,
    semester_financials,
)

# ============================================================
# STATIC DATA
# ============================================================

# weight = relative size of the January intake; female = share of female students
PROGRAMS = [
    dict(code="MVM", name="Motor Vehicle Mechanics", years=3, cat="NC", tuition=260,
         practical=60, practical_name="Practical Materials", weight=14, female=0.05,
         desc="Servicing, diagnosis and repair of light and heavy motor vehicles."),
    dict(code="WELD", name="Welding and Fabrication", years=2, cat="NC", tuition=240,
         practical=60, practical_name="Practical Materials", weight=13, female=0.08,
         desc="Arc, MIG and gas welding, sheet-metal work and structural fabrication."),
    dict(code="ELEC", name="Electrical Installation", years=3, cat="NC", tuition=260,
         practical=50, practical_name="Practical Materials", weight=13, female=0.12,
         desc="Domestic and industrial wiring, installation, testing and maintenance."),
    dict(code="CARP", name="Carpentry and Joinery", years=2, cat="NC", tuition=220,
         practical=55, practical_name="Practical Materials", weight=9, female=0.10,
         desc="Furniture making, roofing, doors and windows, and site carpentry."),
    dict(code="BRICK", name="Bricklaying and Plastering", years=2, cat="NC", tuition=200,
         practical=45, practical_name="Practical Materials", weight=8, female=0.10,
         desc="Brick and block laying, plastering, screeding and building drawings."),
    dict(code="PLUMB", name="Plumbing and Pipe Fitting", years=2, cat="NC", tuition=230,
         practical=50, practical_name="Practical Materials", weight=7, female=0.10,
         desc="Water reticulation, sanitation, drainage and pipe fitting."),
    dict(code="FASH", name="Fashion Design and Garment Construction", years=2, cat="NC",
         tuition=190, practical=35, practical_name="Practical Materials", weight=9, female=0.92,
         desc="Pattern drafting, garment construction, textiles and fashion design."),
    dict(code="CATER", name="Food Production and Catering", years=2, cat="NC", tuition=210,
         practical=45, practical_name="Practical Materials", weight=10, female=0.75,
         desc="Food preparation, baking, menu planning and catering operations."),
    dict(code="HAIR", name="Hairdressing and Beauty Therapy", years=1, cat="NC", tuition=180,
         practical=40, practical_name="Practical Materials", weight=8, female=0.93,
         desc="Hair care and styling, skin care, nail technology and salon management."),
    dict(code="ICT", name="Information and Communication Technology", years=3, cat="NQ",
         tuition=280, practical=35, practical_name="Computer Lab Fee", weight=12, female=0.45,
         desc="Computer hardware, networking, software applications and web basics."),
    dict(code="OFFAD", name="Office Administration and Secretarial", years=2, cat="NQ",
         tuition=200, practical=20, practical_name="Computer Lab Fee", weight=8, female=0.80,
         desc="Records management, secretarial duties, business communication and computing."),
    dict(code="SOLAR", name="Solar PV Installation (Short Course)", years=1, cat="OTHER",
         tuition=170, practical=30, practical_name="Practical Materials", weight=5, female=0.20,
         desc="Design, installation and maintenance of small solar photovoltaic systems."),
]

MALE_NAMES = """Tendai Tafadzwa Farai Tinashe Takudzwa Blessing Munyaradzi Kudakwashe Tapiwa
Simbarashe Panashe Nyasha Brighton Prince Learnmore Lovemore Knowledge Tawanda Takunda Nhamo
Chengetai Gift Innocent Walter Admire Anesu Tatenda Tonderai Wellington Bhekithemba Sibusiso
Nkosana Thulani Themba Mthokozisi Lucky Trymore Vusi Mqondisi Ishmael Shingirai Kuda Tichaona
Ronald Wilson Obert Denford Edmore Misheck Walter Taurai Davison Cleopas Joseph Emmanuel""".split()

FEMALE_NAMES = """Tsitsi Rudo Chipo Ruvimbo Vimbai Nyasha Tariro Shamiso Tatenda Rutendo Memory
Precious Patience Loveness Ruth Sandra Grace Chiedza Tanaka Fadzai Netsai Anesu Nokuthula
Thandiwe Sithembile Nomsa Busisiwe Zodwa Lindiwe Ntombi Latoya Natasha Joyce Rumbidzai Yeukai
Tsungai Kudzai Ropafadzo Definate Sharon Chenai Mercy Faith Hazel Beauty Primrose Gladys Spiwe
Sekai Mutsa Tapiwa Esnath Albertina Rosemary""".split()

SURNAMES = """Moyo Ncube Sibanda Ndlovu Dube Nyoni Mpofu Khumalo Mlambo Mhlanga Chikomba Makoni
Mutasa Chigumba Mukucha Mapuranga Shumba Dzvairo Marufu Gumbo Chuma Makwanya Zvobgo Nyathi
Masvingise Mudzingwa Mazarura Chirwa Banda Phiri Tembo Zhou Mupfumi Maphosa Mavhunga Munyoro
Katsande Mhandu Chidzero Hove Gondo Mutsvairo Nyamhunga Madziva Matsika Chitsa Musariri
Mushonga Tavengwa Kanyemba Mushore Mukwena Muchena Mutema Zimunya Chibaya Manyika Tagwireyi
Murape Gwaze Masuku Mathe Tshuma Ndhlovu Ngwenya Siziba Msimanga Mabhena Mguni Mahachi
Chakanyuka Bvukutwa Mujuru Makamure Mandizha Rusere Samanga Tsvangira Zinyama""".split()

# (suburb, city) pairs; Harare area is weighted heavily
HARARE_SUBURBS = ["Mbare", "Highfield", "Glen View", "Glen Norah", "Budiriro", "Kuwadzana",
                  "Dzivarasekwa", "Mabvuku", "Tafara", "Warren Park", "Hatfield", "Waterfalls",
                  "Epworth", "Mufakose", "Kambuzuma", "Southerton"]
OTHER_PLACES = [("Chitungwiza", "Seke Unit"), ("Ruwa", "Damofalls"), ("Luveve", "Bulawayo"),
                ("Nkulumane", "Bulawayo"), ("Pumula", "Bulawayo"), ("Sakubva", "Mutare"),
                ("Dangamvura", "Mutare"), ("Mkoba", "Gweru"), ("Rujeko", "Masvingo"),
                ("Dombotombo", "Marondera"), ("Chipadze", "Bindura"), ("Rimuka", "Kadoma"),
                ("Cold Comfort", "Chinhoyi"), ("Hobhouse", "Norton")]
DISTRICTS = ["Mutoko", "Murehwa", "Chikomba", "Gokwe", "Zvishavane", "Chipinge", "Buhera",
             "Bikita", "Mt Darwin", "Shamva", "Hwedza", "Umguza"]

ID_CODES = [4, 5, 6, 8, 10, 12, 13, 14, 15, 18, 22, 25, 27, 28, 29, 32, 34, 38, 42, 43, 44, 45,
            47, 48, 50, 53, 58, 59, 61, 63, 66, 67, 70, 71, 75, 79]

WITHDRAW_NOTES = [
    "Withdrew - unable to pay fees", "Withdrew - unable to pay fees",
    "Withdrew - relocated", "Withdrew - found employment",
    "Withdrew - transferred to another college", "Withdrew - family circumstances",
    "Withdrew - health reasons", "Dropped out - no contact",
]
DEFER_NOTES = [
    "Deferred due to fees", "Deferred due to fees", "Deferred - medical",
    "Deferred - family relocation", "Deferred - sponsor withdrew funding",
    "Deferred - personal reasons",
]
RETURN_NOTES = ["Returned from deferment.", "Resumed studies after deferment."]

PROFILES = ["full", "two", "three", "late", "partial", "none"]
# how likely each payer type is to withdraw / defer (relative)
RISK = {"full": 0.5, "two": 0.6, "three": 0.8, "late": 1.6, "partial": 2.2, "none": 3.0}

ACTIVE, DEFERRED, WITHDRAWN, COMPLETED = (
    Student.ACTIVE, Student.DEFERRED, Student.WITHDRAWN, Student.COMPLETED,
)
STATUS_LABEL = dict(Student.STATUS_CHOICES)
METHOD_LABEL = dict(Payment.PAYMENT_METHODS)

MON, FRI = 0, 4


# ============================================================
# SMALL HELPERS
# ============================================================

def round5(x):
    return int(x / 5 + 0.5) * 5


def on_or_after(d, weekday):
    return d + timedelta(days=(weekday - d.weekday()) % 7)


def on_or_before(d, weekday):
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def easter(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


_HOLIDAYS = {}


def zimbabwe_holidays(year):
    if year not in _HOLIDAYS:
        days = set()
        for month, day in [(1, 1), (2, 21), (4, 18), (5, 1), (5, 25), (12, 22), (12, 25), (12, 26)]:
            d = date(year, month, day)
            days.add(d)
            if d.weekday() == 6:  # Sunday holidays roll to Monday
                days.add(d + timedelta(days=1))
        e = easter(year)
        days |= {e - timedelta(days=2), e - timedelta(days=1), e + timedelta(days=1)}
        heroes = on_or_after(date(year, 8, 8), MON)  # second Monday of August
        days |= {heroes, heroes + timedelta(days=1)}
        _HOLIDAYS[year] = days
    return _HOLIDAYS[year]


def business_day(d, back=False):
    step = timedelta(days=-1 if back else 1)
    while d.weekday() >= 5 or d in zimbabwe_holidays(d.year):
        d += step
    return d


def semester_dates(year):
    return {
        1: (on_or_after(date(year, 1, 10), MON), on_or_before(date(year, 6, 28), FRI)),
        2: (on_or_after(date(year, 7, 17), MON), on_or_after(date(year, 11, 28), FRI)),
    }


@contextmanager
def backdating_allowed():
    """Let us set created_at / enrolled_at / timestamp / date_changed explicitly.

    The models use auto_now_add, which always stamps "now". For seeded history we
    want the real event dates, so the flags are switched off while seeding and
    restored afterwards.
    """
    patched = []
    for model in (Student, StudentStatusLog, Enrollment, StudentCharge, Payment, AuditLog):
        for f in model._meta.concrete_fields:
            if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False):
                patched.append((f, f.auto_now, f.auto_now_add))
                f.auto_now = False
                f.auto_now_add = False
    try:
        yield
    finally:
        for f, auto_now, auto_now_add in patched:
            f.auto_now = auto_now
            f.auto_now_add = auto_now_add


# ============================================================
# IN-MEMORY SIMULATION OBJECTS
# ============================================================

@dataclass
class Plan:
    """Everything we decide about a student before touching the database."""
    program: object
    intake_year: int
    enroll_year: int          # academic year of the first enrollment
    start_sem_no: int
    start_level: int
    reg_dt: datetime
    legacy: bool
    person: dict
    profile: str
    number: str = ""


@dataclass
class Spec:
    """One semester enrollment (plus its charges and planned payments)."""
    sem: object
    level: int
    created: datetime
    items: list
    status: str = Enrollment.ACTIVE
    charged: bool = True       # False once a withdrawal has cleared the charges
    profile: str = "full"
    total: int = 0
    payments: list = field(default_factory=list)   # [(date, amount, kind, idx, n)]
    enrollment: object = None


@dataclass
class Sim:
    specs: list = field(default_factory=list)
    logs: list = field(default_factory=list)      # (dt, status, note)
    audits: list = field(default_factory=list)    # (dt, username, action, summary, details, category)
    status: str = ACTIVE


# ============================================================
# THE SEEDER
# ============================================================

class Seeder:
    def __init__(self, rng, today, years, intake, password, out):
        self.rng = rng
        self.today = today
        self.years = years
        self.intake = intake
        self.password = password
        self.out = out

        self.use_tz = settings.USE_TZ
        self.now = timezone.now() if self.use_tz else datetime.now()
        self.cur_year = today.year
        self.first_year = today.year - years + 1

        self.users = {}
        self.ay = {}          # year -> AcademicYear
        self.sems = {}        # (year, number) -> Semester
        self.programs = []
        self.fee_items = {}   # (program_id, level, semester_id) -> [FeeStructureItem]
        self.progress_dt = {}  # year -> datetime of the bulk progression into that year

        self.charges = []
        self.status_logs = []
        self.audits = []
        self.pending_payments = []
        self.stats = {"students": 0, "enrollments": 0, "payments": 0}

    # ---------- time helpers ----------

    def make_dt(self, d, hour=9, minute=0, second=0):
        dt = datetime(d.year, d.month, d.day, hour, minute, second)
        return timezone.make_aware(dt) if self.use_tz else dt

    def office_dt(self, d):
        """A random time within office hours (07:45-16:30) on date d, never in the future."""
        minutes = self.rng.randint(7 * 60 + 45, 16 * 60 + 30)
        dt = self.make_dt(d, minutes // 60, minutes % 60, self.rng.randint(0, 59))
        if dt > self.now:
            dt = self.now - timedelta(minutes=self.rng.randint(2, 90))
        return dt

    def bday(self, d, back=False):
        return business_day(d, back=back)

    # ---------- phase 1: users ----------

    def make_users(self):
        User = get_user_model()
        for username, first, last in [
            ("registrar", "Rudo", "Mutasa"),
            ("bursar", "Tendai", "Chikomba"),
            ("cashier1", "Nyasha", "Ndlovu"),
            ("cashier2", "Sibusiso", "Moyo"),
        ]:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "is_staff": False},
            )
            if created:
                if self.password:
                    user.set_password(self.password)
                else:
                    user.set_unusable_password()
                user.save()
            self.users[username] = user

    def pick_cashier(self):
        return self.rng.choices(["cashier1", "cashier2", "bursar"], weights=[45, 40, 15])[0]

    # ---------- phase 2: calendar ----------

    def make_calendar(self):
        for year in range(self.first_year - 2, self.cur_year + 1):
            ay = AcademicYear(
                name=str(year),
                start_date=date(year, 1, 1),
                end_date=date(year, 12, 31),
                is_current=(year == self.cur_year),
            )
            ay.save()
            self.ay[year] = ay
            if year < self.first_year:
                continue  # earlier years only exist as the intake year of legacy students
            for number, (start, end) in semester_dates(year).items():
                sem = Semester(academic_year=ay, number=number, start_date=start, end_date=end)
                sem.save()
                self.sems[(year, number)] = sem

        # the one-per-year bulk progression run (previous S2 -> next S1)
        for year in range(self.first_year + 1, self.cur_year + 1):
            prev_end = self.sems[(year - 1, 2)].end_date
            run = prev_end + timedelta(days=self.rng.randint(5, 20))
            run = min(run, self.sems[(year, 1)].start_date - timedelta(days=4))
            self.progress_dt[year] = self.make_dt(
                self.bday(run), 9 + self.rng.randint(0, 2), self.rng.randint(0, 59)
            )

    def next_semester_start(self, sem):
        year, number = sem.academic_year.name, sem.number
        year = int(year)
        key = (year, 2) if number == 1 else (year + 1, 1)
        nxt = self.sems.get(key)
        return nxt.start_date if nxt else None

    # ---------- phase 3: programs and fees ----------

    def make_programs_and_fees(self):
        for spec in PROGRAMS:
            program = Program.objects.create(
                code=spec["code"], name=spec["name"], description=spec["desc"],
                duration_years=spec["years"], category=spec["cat"], active=True,
            )
            program.seed = spec
            self.programs.append(program)

        for (year, number), sem in self.sems.items():
            inflation = 1.07 ** (year - self.first_year)
            for program in self.programs:
                s = program.seed
                for level in range(1, program.duration_years + 1):
                    structure = FeeStructure.objects.create(
                        program=program, year_level=level, semester=sem
                    )
                    lines = [
                        ("Tuition", f"Semester tuition - year {level}",
                         round5(s["tuition"] * inflation * (1 + 0.06 * (level - 1)))),
                        ("Levy", "Library, sports and student services levy", round5(25 * inflation)),
                    ]
                    if s["practical"]:
                        lines.append((s["practical_name"], "Workshop / lab consumables",
                                      round5(s["practical"] * inflation)))
                    if number == 2:
                        lines.append(("Examination Fee", "National trade test and examination fees",
                                      round5(35 * inflation)))
                    if number == 1 and level == 1:
                        lines.append(("Registration Fee", "One-off registration and student ID",
                                      round5(20 * inflation)))
                    items = [
                        FeeStructureItem.objects.create(
                            fee_structure=structure, name=name, description=desc,
                            amount=Decimal(amount).quantize(Decimal("0.01")),
                        )
                        for name, desc, amount in lines
                    ]
                    self.fee_items[(program.pk, level, sem.pk)] = items

    # ---------- phase 4: planning students ----------

    def profile_weights(self, year):
        i = max(0, min(2, year - self.first_year))
        return [26 - 3 * i, 22 - i, 18, 17 + i, 11 + 2 * i, 6 + i]

    def pick_profile(self, year):
        return self.rng.choices(PROFILES, weights=self.profile_weights(year))[0]

    def make_person(self, program, legacy_import):
        rng = self.rng
        for _ in range(8):
            gender = "FEMALE" if rng.random() < program.seed["female"] else "MALE"
            first = rng.choice(FEMALE_NAMES if gender == "FEMALE" else MALE_NAMES)
            last = rng.choice(SURNAMES)
            if (first, last) not in self._seen_names:
                break
        self._seen_names.add((first, last))
        person = dict(first_name=first, last_name=last, gender=gender, national_id="",
                      date_of_birth=None, guardian_name="", guardian_phone="",
                      student_phone="", address="")
        if legacy_import and rng.random() < 0.7:
            return person  # spreadsheet imports only carry names; details are filled in later

        age = rng.choices(range(16, 30), weights=[4, 11, 17, 18, 14, 10, 8, 5, 4, 3, 2, 2, 1, 1])[0]
        person["date_of_birth"] = date(self.first_year, 1, 1) - timedelta(days=age * 365 + rng.randint(0, 364))
        if rng.random() < 0.97:
            person["national_id"] = "{:02d}-{} {} {:02d}".format(
                rng.choice(ID_CODES), rng.randint(100000, 9999999),
                rng.choice("ABCDEFGHJKLMNPQRSTVWXYZ"), rng.choice(ID_CODES),
            )
        if rng.random() > 0.08:
            person["student_phone"] = self.phone()
        if rng.random() > (0.40 if age >= 22 else 0.05):
            guardian_last = last if rng.random() < 0.85 else rng.choice(SURNAMES)
            guardian_first = rng.choice(MALE_NAMES + FEMALE_NAMES)
            person["guardian_name"] = f"{guardian_first} {guardian_last}"
            if rng.random() > 0.08:
                person["guardian_phone"] = self.phone()
        person["address"] = self.address(last) if rng.random() > 0.04 else ""
        return person

    def phone(self):
        return "{} {} {}".format(
            self.rng.choice(["077", "077", "078", "078", "071", "073"]),
            self.rng.randint(100, 999), self.rng.randint(1000, 9999),
        )

    def address(self, surname):
        rng = self.rng
        r = rng.random()
        if r < 0.06:
            return f"{surname} Village, Ward {rng.randint(1, 24)}, {rng.choice(DISTRICTS)} District"
        if r < 0.72:
            suburb, city = rng.choice(HARARE_SUBURBS), "Harare"
        else:
            suburb, city = rng.choice(OTHER_PLACES)
        if rng.random() < 0.5:
            return f"{rng.randint(1, 9999)} {suburb} {rng.randint(1, 8)}, {city}"
        ordinal = {1: "st", 2: "nd", 3: "rd"}.get(rng.randint(1, 12), "th")
        n = rng.randint(1, 12)
        ordinal = {1: "st", 2: "nd", 3: "rd"}.get(n, "th")
        return f"House {rng.randint(1, 999)}, {n}{ordinal} Street, {suburb}, {city}"

    def plan_students(self):
        rng = self.rng
        self._seen_names = set()
        total_weight = sum(p.seed["weight"] for p in self.programs)
        plans = []

        def new_plan(program, intake_year, enroll_year, sem_no, level, reg_dt, legacy):
            return Plan(
                program=program, intake_year=intake_year, enroll_year=enroll_year,
                start_sem_no=sem_no, start_level=level, reg_dt=reg_dt, legacy=legacy,
                person=self.make_person(program, legacy),
                profile=self.pick_profile(enroll_year),
            )

        for year in range(self.first_year, self.cur_year + 1):
            growth = 1 + 0.05 * (year - self.first_year)
            s1, s2 = self.sems[(year, 1)], self.sems[(year, 2)]
            for program in self.programs:
                share = program.seed["weight"] / total_weight
                n_main = max(1, round(self.intake * share * growth * rng.uniform(0.9, 1.1)))
                n_mid = round(n_main * rng.uniform(0.06, 0.14))
                for _ in range(n_main):
                    off = max(-45, min(35, int(rng.gauss(-4, 11))))
                    d = self.bday(s1.start_date + timedelta(days=off))
                    plans.append(new_plan(program, year, year, 1, 1, self.office_dt(d), False))
                for _ in range(n_mid):
                    off = max(-30, min(28, int(rng.gauss(-5, 8))))
                    d = self.bday(s2.start_date + timedelta(days=off))
                    plans.append(new_plan(program, year, year, 2, 1, self.office_dt(d), False))

        # legacy cohorts, imported into the first seeded year at year level 2 / 3
        first_s1 = self.sems[(self.first_year, 1)]
        import_day = self.bday(first_s1.start_date - timedelta(days=6), back=True)
        self.import_dt = {}
        for level, keep in ((2, 0.75), (3, 0.60)):
            base = self.make_dt(import_day, 10, 15 + level)
            self.import_dt[level] = base
            i = 0
            for program in self.programs:
                if program.duration_years < level:
                    continue
                share = program.seed["weight"] / total_weight
                n = round(self.intake * share * keep * rng.uniform(0.9, 1.1))
                for _ in range(n):
                    plans.append(new_plan(
                        program, self.first_year - (level - 1), self.first_year, 1, level,
                        base + timedelta(milliseconds=25 * i), True,
                    ))
                    i += 1

        plans = [p for p in plans if p.reg_dt.date() <= self.today]
        plans.sort(key=lambda p: p.reg_dt)

        counters = {}
        for p in plans:
            counters[p.intake_year] = counters.get(p.intake_year, 0) + 1
            p.number = f"{p.intake_year % 100:02d}-{counters[p.intake_year]:04d}"
        return plans

    # ---------- phase 5: simulating one student ----------

    def plan_payments(self, profile, total, sem, earliest, cutoff, reg_hint=None):
        """Return [(date, amount)] the family intends to pay for one semester."""
        rng = self.rng
        start, end = sem.start_date, sem.end_date
        span = (end - start).days
        total = int(total)
        if total <= 0:
            return []

        def at(lo, hi):
            d = start + timedelta(days=rng.randint(lo, max(lo, hi)))
            return self.bday(max(d, earliest))

        first = at(-21, 21)
        if reg_hint is not None and rng.random() < 0.6:
            first = self.bday(max(reg_hint, earliest) + timedelta(days=rng.randint(0, 9)))

        fractions = []   # [(date, fraction of total)]
        if profile == "full":
            if rng.random() < 0.15:
                fractions = [(first, 0.7), (self.bday(first + timedelta(days=rng.randint(3, 12))), 0.3)]
            else:
                fractions = [(first, 1.0)]
        elif profile == "two":
            f1 = rng.choice([0.5, 0.6, 0.65])
            fractions = [(first, f1), (at(35, min(90, span - 21)), 1 - f1)]
        elif profile == "three":
            f1 = rng.choice([0.4, 0.5])
            rest = (1 - f1) / 2
            fractions = [(first, f1), (at(30, 50), rest), (at(75, min(110, span - 14)), rest)]
        elif profile == "late":
            grand = rng.uniform(0.75, 1.0)
            f1 = rng.choice([0.25, 0.3, 0.4])
            fractions = [(first, f1), (at(span - 60, span - 15), grand - f1)]
        elif profile == "partial":
            grand = rng.uniform(0.35, 0.8)
            k = rng.choice([1, 1, 2, 3])
            dates = [first] + [at(25 + 30 * j, 55 + 30 * j) for j in range(k - 1)]
            fractions = [(d, grand / k) for d in dates]
        elif profile == "none":
            if rng.random() < 0.25:
                fractions = [(first, rng.choice([0.1, 0.15, 0.2]))]

        if not fractions:
            return []
        grand_total = total if abs(sum(f for _, f in fractions) - 1.0) < 1e-9 else round5(total * sum(f for _, f in fractions))
        dates = sorted(d for d, _ in fractions)
        amounts = [round5(total * f) for _, f in fractions[:-1]]
        amounts.append(grand_total - sum(amounts))
        out = []
        for d, amount in zip(dates, amounts):
            if amount > 0 and d <= cutoff and d <= self.today:
                out.append((d, amount))
        return out

    def plan_arrears(self, spec, remaining, allowed):
        rng = self.rng
        r = rng.random()
        if r < 0.50:
            amount = remaining
        elif r < 0.70:
            amount = max(5, min(remaining, round5(remaining * rng.uniform(0.3, 0.7))))
        else:
            return []
        end = spec.sem.end_date
        nxt = self.next_semester_start(spec.sem)
        if nxt and rng.random() < 0.7:
            d = nxt + timedelta(days=rng.randint(-14, 30))
        else:
            d = end + timedelta(days=rng.randint(10, 270))
        d = self.bday(max(d, end + timedelta(days=7)))
        if d > self.today or not allowed(d):
            return []
        return [(d, amount)]

    def simulate(self, plan, student_index):
        rng, today, program = self.rng, self.today, plan.program
        sim = Sim()
        sim.logs.append((plan.reg_dt, ACTIVE,
                         "Imported from spreadsheet." if plan.legacy else "Initial registration."))
        if not plan.legacy:
            sim.audits.append((
                plan.reg_dt, "registrar", "REGISTER",
                f"Registered student {plan.person['first_name']} {plan.person['last_name']}",
                {"student_number": plan.number, "program": program.name,
                 "intake_year": str(plan.intake_year), "year_level": plan.start_level},
                "STUDENT",
            ))

        level, year = plan.start_level, plan.enroll_year
        start_no = plan.start_sem_no
        created = plan.reg_dt
        profile = plan.profile
        blocked = []   # payment blackout windows (deferred / withdrawn)
        first_loop = True

        def allowed(d):
            return not any(a <= d < b for a, b in blocked)

        while True:
            sems = [self.sems[(year, n)] for n in (1, 2) if n >= start_no]
            specs = [Spec(sem, level, created, self.fee_items.get((program.pk, level, sem.pk), []))
                     for sem in sems]
            for spec in specs:
                if rng.random() < 0.2:
                    profile = self.pick_profile(year)
                spec.profile = profile
                spec.total = int(sum(i.amount for i in spec.items))
            sim.specs.extend(specs)

            # --- does something happen to this student during the year? ---
            event = None
            for spec in specs:
                sem = spec.sem
                lo = max(sem.start_date + timedelta(days=14), created.date())
                hi = min(sem.end_date - timedelta(days=7), today)
                if hi < lo:
                    continue
                risk = RISK[spec.profile]
                p_withdraw = (0.022 if sem.number == 1 else 0.026) * risk
                p_defer = 0.008 * risk
                r = rng.random()
                if r < p_withdraw:
                    kind = "W"
                elif r < p_withdraw + p_defer:
                    kind = "D"
                else:
                    continue
                when = self.bday(lo + timedelta(days=rng.randint(0, (hi - lo).days)))
                if when > hi:
                    when = self.bday(hi, back=True)
                if when < lo:
                    continue
                event = (kind, when)
                break

            cutoff = event[1] if event else today
            for i, spec in enumerate(specs):
                hint = created.date() if (first_loop and i == 0 and not plan.legacy) else None
                plans = self.plan_payments(spec.profile, spec.total, spec.sem,
                                           created.date(), cutoff, hint)
                n = len(plans)
                spec.payments = [(d, a, "regular", idx, n) for idx, (d, a) in enumerate(plans)]
            first_loop = False

            if event and event[0] == "W":
                when = event[1]
                dt = self.office_dt(when)
                affected = [s for s in specs if s.sem.end_date >= when]
                removed = sum(len(s.items) for s in affected)
                for s in affected:
                    s.charged = False
                if removed:
                    sim.audits.append((
                        dt, "registrar", "WITHDRAWAL",
                        f"Cleared {removed} future charges for withdrawn student",
                        {"semesters_affected": sorted((s.sem.pk for s in affected), reverse=True),
                         "charges_removed": removed},
                        "FINANCIAL",
                    ))
                note = rng.choice(WITHDRAW_NOTES)
                dt2 = dt + timedelta(seconds=1)
                sim.logs.append((dt2, WITHDRAWN, note))
                sim.audits.append((
                    dt2, "registrar", "STATUS_CHANGE",
                    f"Status changed from {STATUS_LABEL[ACTIVE]} to {STATUS_LABEL[WITHDRAWN]}",
                    {"old_status": ACTIVE, "new_status": WITHDRAWN, "note": note}, "STUDENT",
                ))
                sim.status = WITHDRAWN
                blocked.append((when, date.max))
                break

            if event and event[0] == "D":
                when = event[1]
                dt = self.office_dt(when)
                note = rng.choice(DEFER_NOTES)
                sim.logs.append((dt, DEFERRED, note))
                sim.audits.append((
                    dt, "registrar", "STATUS_CHANGE",
                    f"Status changed from {STATUS_LABEL[ACTIVE]} to {STATUS_LABEL[DEFERRED]}",
                    {"old_status": ACTIVE, "new_status": DEFERRED, "note": note}, "STUDENT",
                ))
                sim.status = DEFERRED
                back = None
                nxt = year + 1
                if nxt <= self.cur_year and rng.random() < 0.5 and self.progress_dt.get(nxt):
                    pdate = self.progress_dt[nxt].date()
                    if pdate <= today:
                        cand = min(pdate + timedelta(days=rng.randint(2, 12)),
                                   self.sems[(nxt, 1)].start_date - timedelta(days=1))
                        cand = self.bday(cand)
                        if cand <= today:
                            back = cand
                blocked.append((when, back or date.max))
                if back is None:
                    break
                back_dt = self.office_dt(back)
                note = rng.choice(RETURN_NOTES)
                sim.logs.append((back_dt, ACTIVE, note))
                sim.audits.append((
                    back_dt, "registrar", "STATUS_CHANGE",
                    f"Status changed from {STATUS_LABEL[DEFERRED]} to {STATUS_LABEL[ACTIVE]}",
                    {"old_status": DEFERRED, "new_status": ACTIVE, "note": note}, "STUDENT",
                ))
                sim.status = ACTIVE
                created, year, start_no = back_dt, nxt, 1   # repeats the same level
                continue

            # --- end of year: the bulk progression run ---
            if year >= self.cur_year:
                break
            run = self.progress_dt.get(year + 1)
            if run is None or run.date() > today:
                break
            run_dt = run + timedelta(milliseconds=30 * student_index)
            if level + 1 > program.duration_years:
                sim.status = COMPLETED
                sim.logs.append((run_dt, COMPLETED,
                                 f"Completed {program.name} after {specs[-1].sem}."))
                break
            specs[-1].status = Enrollment.COMPLETED
            level, year, start_no, created = level + 1, year + 1, 1, run_dt

        # --- arrears: settled (or not) after a semester has ended ---
        for spec in sim.specs:
            if not spec.charged or spec.sem.end_date >= today:
                continue
            remaining = spec.total - sum(a for _, a, *_ in spec.payments)
            if remaining <= 0:
                continue
            for d, amount in self.plan_arrears(spec, remaining, allowed):
                spec.payments.append((d, amount, "arrears", 0, 1))
        return sim

    # ---------- phase 6: writing to the database ----------

    def persist_student(self, plan, sim):
        person = plan.person
        student = Student(
            student_number=plan.number, program=plan.program,
            intake_year=self.ay[plan.intake_year], status=sim.status,
            created_at=plan.reg_dt, **person,
        )
        student.save()
        self.stats["students"] += 1

        for spec in sim.specs:
            enrollment = Enrollment(
                student=student, program=plan.program, semester=spec.sem,
                year_level=spec.level, status=spec.status, enrolled_at=spec.created,
            )
            enrollment.save()
            spec.enrollment = enrollment
            self.stats["enrollments"] += 1
            if spec.charged:
                for item in spec.items:
                    self.charges.append(StudentCharge(
                        student=student, enrollment=enrollment, fee_item=item,
                        amount=item.amount, created_at=spec.created,
                    ))
            for d, amount, kind, idx, n in spec.payments:
                self.pending_payments.append((d, student.pk, student, spec, amount, kind, idx, n))

        for dt, status, note in sim.logs:
            self.status_logs.append(StudentStatusLog(
                student=student, status=status, note=note, date_changed=dt))
        for dt, username, action, summary, details, category in sim.audits:
            self.audits.append(AuditLog(
                user=self.users[username], action=action, student=student, timestamp=dt,
                summary=summary, details=details, category=category))
        return student

    def pick_method(self, year, amount):
        i = max(0, min(2, year - self.first_year))
        w = {"CASH": [46, 41, 37][i], "ECOCASH": [30, 36, 41][i], "BANK": [20, 19, 18][i], "OTHER": 4}
        if amount >= 250:
            w["BANK"] *= 1.8
            w["ECOCASH"] *= 0.7
        if amount >= 450:
            w["ECOCASH"] *= 0.4
        return self.rng.choices(list(w), weights=list(w.values()))[0]

    def reference_for(self, method, d, cdt):
        rng = self.rng
        if method == "BANK":
            return str(rng.randint(100000, 9999999))
        if method == "ECOCASH":
            return "MP{:%y%m%d}.{:%H%M}.{}{}".format(
                d, cdt, rng.choice("ABCDEFGHJKLMNPQRSTUVWXY"), rng.randint(10000, 99999))
        if method == "OTHER":
            return rng.choice(["OneMoney", "InnBucks", "Zipit", "Sponsor cheque",
                               "Cash deposit by guardian"])
        return ""

    def note_for(self, kind, idx, n, spec, paid_so_far, amount):
        rng, r = self.rng, self.rng.random()
        if kind == "arrears":
            return f"Arrears - {spec.sem}" if r < 0.6 else ""
        if n == 1 and paid_so_far + amount >= spec.total:
            return "Paid in full" if r < 0.2 else ""
        if idx == 0 and n > 1:
            return "Part payment - balance to follow" if r < 0.3 else ""
        if idx == n - 1 and paid_so_far + amount >= spec.total:
            return "Balance cleared" if r < 0.3 else ""
        return "Paid by sponsor" if r < 0.03 else ""

    def persist_payments(self):
        rng = self.rng
        self.pending_payments.sort(key=lambda p: (p[0], p[1], p[3].sem.pk))
        running = {}   # (student_pk, semester_pk) -> paid so far, for notes
        for d, _, student, spec, amount, kind, idx, n in self.pending_payments:
            key = (student.pk, spec.sem.pk)
            paid_before = running.get(key, 0)
            running[key] = paid_before + amount

            method = self.pick_method(d.year, amount)
            cdt = self.office_dt(d)
            enrolled_at = spec.created
            if cdt <= enrolled_at:
                cdt = min(enrolled_at + timedelta(minutes=rng.randint(5, 90)), self.now)
            payment = Payment(
                student=student, semester=spec.sem,
                amount=Decimal(amount).quantize(Decimal("0.01")),
                payment_date=d, method=method,
                reference=self.reference_for(method, d, cdt),
                notes=self.note_for(kind, idx, n, spec, paid_before, amount),
                created_at=cdt,
            )
            payment.save()   # receipt number is allocated by Payment.save()
            self.stats["payments"] += 1
            self.audits.append(AuditLog(
                user=self.users[self.pick_cashier()], action="PAYMENT", student=student,
                timestamp=min(cdt + timedelta(seconds=1), self.now),
                summary=(f"Payment of {payment.amount} recorded for "
                         f"{payment.semester} (receipt {payment.receipt_number})"),
                details={"receipt": payment.receipt_number, "amount": str(payment.amount),
                         "semester": str(payment.semester), "method": METHOD_LABEL[method],
                         "reference": payment.reference},
                category="FINANCIAL",
            ))

    def flush_bulk(self):
        # bulk imports are logged once per spreadsheet in the app
        first_s1 = self.sems[(self.first_year, 1)]
        for level, dt in self.import_dt.items():
            count = sum(1 for a in self.audits if False)  # placeholder, replaced below
        StudentCharge.objects.bulk_create(self.charges, batch_size=1000)
        StudentStatusLog.objects.bulk_create(self.status_logs, batch_size=1000)
        self.audits.sort(key=lambda a: a.timestamp)
        AuditLog.objects.bulk_create(self.audits, batch_size=1000)

    def add_import_audits(self, plans):
        first_s1 = self.sems[(self.first_year, 1)]
        for level, dt in self.import_dt.items():
            count = sum(1 for p in plans if p.legacy and p.start_level == level)
            if not count:
                continue
            self.audits.append(AuditLog(
                user=self.users["registrar"], action="OTHER", student=None,
                timestamp=dt + timedelta(minutes=2),
                summary=f"Bulk-imported {count} student(s) from spreadsheet",
                details={"count": count, "intake_year": str(self.first_year - (level - 1)),
                         "semester": str(first_s1), "skipped": []},
                category="STUDENT",
            ))

    # ---------- orchestration ----------

    def run(self):
        steps = [
            ("staff users", self.make_users),
            ("academic years and semesters", self.make_calendar),
            ("programs and fee structures", self.make_programs_and_fees),
        ]
        for label, fn in steps:
            self.out.write(f"  {label}...")
            fn()

        self.out.write("  planning students...")
        plans = self.plan_students()
        self.out.write(f"  simulating and saving {len(plans)} students...")
        for i, plan in enumerate(plans):
            sim = self.simulate(plan, i)
            self.persist_student(plan, sim)

        self.add_import_audits(plans)
        self.out.write(f"  recording {len(self.pending_payments)} payments...")
        self.persist_payments()
        self.out.write("  writing charges, status logs and audit entries...")
        self.flush_bulk()


# ============================================================
# MANAGEMENT COMMAND
# ============================================================

class Command(BaseCommand):
    help = "Seed believable demo data (students, fees, payments, audit trail) up to today."

    def add_arguments(self, parser):
        parser.add_argument("--years", type=int, default=3,
                            help="Academic years to seed, ending with the current one (default 3).")
        parser.add_argument("--intake", type=int, default=260,
                            help="Approximate January intake across all programs (default 260).")
        parser.add_argument("--seed", type=int, default=42,
                            help="Random seed for repeatable data (default 42).")
        parser.add_argument("--flush", action="store_true",
                            help="Delete ALL existing school data before seeding.")
        parser.add_argument("--noinput", action="store_true",
                            help="Do not ask for confirmation when using --flush.")
        parser.add_argument("--password", default=None,
                            help="Password for the demo staff users (default: unusable).")

    def handle(self, *args, **opts):
        if opts["years"] < 1 or opts["years"] > 6:
            raise CommandError("--years must be between 1 and 6.")

        models_in_order = [AuditLog, StudentCharge, Payment, StudentStatusLog, Enrollment,
                           Student, FeeStructureItem, FeeStructure, Semester, AcademicYear,
                           Program]
        has_data = any(m.objects.exists() for m in models_in_order)

        if has_data and not opts["flush"]:
            raise CommandError(
                "The school tables already contain data. Re-run with --flush to wipe them "
                "first, or seed into an empty database."
            )
        if opts["flush"] and has_data:
            if not opts["noinput"]:
                answer = input("This will DELETE all programs, students, fees, payments and "
                               "audit entries. Type 'yes' to continue: ")
                if answer.strip().lower() != "yes":
                    raise CommandError("Cancelled.")
            with transaction.atomic():
                for model in models_in_order:
                    model.objects.all().delete()
            self.stdout.write("Existing school data deleted.")

        today = timezone.localdate()
        try:
            frozen = TimeOverride.get_frozen_time()
        except Exception:
            frozen = None
        if frozen:
            self.stdout.write(self.style.WARNING(
                f"Note: the app clock is frozen at {frozen:%Y-%m-%d}. Data is seeded up to the "
                f"real date ({today}); clear the time override to see it as 'current'."
            ))

        self.stdout.write(f"Seeding {opts['years']} academic year(s) up to {today} "
                          f"(seed={opts['seed']})...")
        seeder = Seeder(random.Random(opts["seed"]), today, opts["years"], opts["intake"],
                        opts["password"], self.stdout)
        with backdating_allowed(), transaction.atomic():
            seeder.run()

        self.report(seeder)

    def report(self, seeder):
        w = self.stdout.write
        w(self.style.SUCCESS("\nDone."))
        s = seeder.stats
        w(f"  {Program.objects.count()} programs, {s['students']} students, "
          f"{s['enrollments']} enrollments, {StudentCharge.objects.count()} charges, "
          f"{s['payments']} payments, {AuditLog.objects.count()} audit entries")
        by_status = {}
        for st in Student.objects.values_list("status", flat=True):
            by_status[st] = by_status.get(st, 0) + 1
        w("  Student status: " + ", ".join(f"{k.title()} {v}" for k, v in sorted(by_status.items())))
        w("\n  Semester            charged        paid  outstanding  collected")
        for (year, number), sem in sorted(seeder.sems.items()):
            f = semester_financials(sem)
            w("  {:<18} {:>9,.0f} {:>11,.0f} {:>12,.0f} {:>9.1f}%".format(
                str(sem), f["charged"], f["paid"], f["outstanding"], f["collection_rate"]))
        w("\n  Staff users created: registrar, bursar, cashier1, cashier2 "
          "(assign them to your role groups).")
