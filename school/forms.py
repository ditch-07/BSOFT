from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    AcademicYear,
    Semester,
    Program,
    FeeStructure,
    FeeStructureItem,
    Student,
    Enrollment,
    Payment,
)


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Select):
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (existing + " form-select").strip()
            elif isinstance(widget, forms.CheckboxInput):
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (existing + " form-check-input").strip()
            else:
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (existing + " form-control").strip()


# ============================================================
# ACADEMIC YEAR / SEMESTER
# ============================================================

class AcademicYearForm(BootstrapFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate year choices: 10 years back and 10 years forward
        current_year = timezone.now().year
        years = range(current_year - 10, current_year + 11)
        choices = [(str(y), str(y)) for y in years]
        self.fields['name'].widget = forms.Select(choices=choices)
        # Set initial to current year for new records
        if not self.instance.pk:
            self.fields['name'].initial = str(current_year)

    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "is_current"]
        widgets = {
            "start_date": forms.DateInput(
                attrs={"class": "form-control datepicker", "type": "text", "autocomplete": "off", "placeholder": "YYYY-MM-DD"},
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={"class": "form-control datepicker", "type": "text", "autocomplete": "off", "placeholder": "YYYY-MM-DD"},
                format="%Y-%m-%d",
            ),
        }


class SemesterForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Semester
        fields = ["academic_year", "number", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(
                attrs={
                    "class": "form-control datepicker",
                    "type": "text",
                    "autocomplete": "off",
                    "placeholder": "YYYY-MM-DD",
                },
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={
                    "class": "form-control datepicker",
                    "type": "text",
                    "autocomplete": "off",
                    "placeholder": "YYYY-MM-DD",
                },
                format="%Y-%m-%d",
            ),
        }


# ============================================================
# PROGRAM (replaces Course)
# ============================================================

class ProgramForm(BootstrapFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["category"].initial = "NC"

    class Meta:
        model = Program
        fields = ["code", "name", "description", "duration_years", "category", "active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


# ============================================================
# FEE STRUCTURE (replaces SemesterFee)
# A FeeStructure is Program + Year Level + Semester.
# FeeStructureItem rows (Tuition, Levy, etc.) hang off it.
# ============================================================

class TradeChoiceField(forms.ModelChoiceField):
    """Show the trade's name; the code is rendered as muted secondary text."""

    def label_from_instance(self, obj):
        return obj.name


class TradeMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.name


def _max_active_duration():
    return (
        Program.objects.filter(active=True).aggregate(max_years=Max("duration_years"))["max_years"]
        or 1
    )


class FeeStructureForm(BootstrapFormMixin, forms.ModelForm):
    """
    Semester is NOT included here on purpose — it's always fixed by the
    URL (/semesters/<id>/fee-structures/new/) and set on the instance
    before the form is bound. Only Trade + Course year are chosen here.
    """

    program = TradeChoiceField(
        queryset=Program.objects.filter(active=True).order_by("name"),
        label="Trade",
        empty_label="Select a trade",
    )
    year_level = forms.TypedChoiceField(
        label="Course year",
        coerce=int,
        empty_value="",
    )

    class Meta:
        model = FeeStructure
        fields = ["program", "year_level"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_years = _max_active_duration()
        if self.instance and self.instance.pk:
            max_years = max(max_years, self.instance.year_level)
        self.fields["year_level"].choices = [("", "Select a course year")] + [
            (level, f"Course year {level}") for level in range(1, max_years + 1)
        ]

    def clean_year_level(self):
        year_level = self.cleaned_data.get("year_level")
        program = self.cleaned_data.get("program")
        if not year_level:
            return year_level
        if program and year_level > program.duration_years:
            raise ValidationError(
                f"{program.name} only runs for {program.duration_years} course year(s)."
            )
        return year_level


class FeeStructureItemForm(forms.ModelForm):
    class Meta:
        model = FeeStructureItem
        fields = ["name", "description", "amount"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Tuition",
                    "autocomplete": "off",
                    "list": "fee-name-options",
                }
            ),
            "description": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Optional note"}
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }
            ),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Give this fee line a name.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        fee_structure = None
        try:
            fee_structure = self.instance.fee_structure
        except FeeStructureItem.fee_structure.RelatedObjectDoesNotExist:
            fee_structure = None

        # Check for duplicate fee names within the same fee structure.
        # This must be safe even before the parent FeeStructure has been saved.
        if name and fee_structure:
            existing = FeeStructureItem.objects.filter(
                fee_structure=fee_structure,
                name__iexact=name,
            ).exclude(pk=self.instance.pk)

            if existing.exists():
                self.add_error(
                    'name',
                    f"A fee line named '{name}' already exists here.",
                )

        return cleaned_data


class FeeStructureItemBaseFormSet(forms.BaseInlineFormSet):
    """Custom formset to validate for duplicate fee names within a fee structure."""
    
    def clean(self):
        super().clean()

        kept_forms = []
        seen_names = {}
        for i, form in enumerate(self.forms):
            if not getattr(form, "cleaned_data", None):
                continue

            if form.cleaned_data.get('DELETE'):
                # Charges protect a fee line: block removal instead of
                # letting save() raise ProtectedError.
                if form.instance.pk and form.instance.student_charges.exists():
                    charged = form.instance.student_charges.count()
                    form.add_error(
                        None,
                        f"{charged} student{'s have' if charged != 1 else ' has'} been charged "
                        "this fee, so it cannot be removed.",
                    )
                continue

            name = form.cleaned_data.get('name')
            if name:
                key = name.casefold()
                if key in seen_names:
                    form.add_error(
                        'name',
                        f"Duplicate fee line name '{name}'. Already used in row {seen_names[key] + 1}.",
                    )
                else:
                    seen_names[key] = i
            if name or form.cleaned_data.get('amount'):
                kept_forms.append(form)

        if not kept_forms and not any(self.errors):
            raise ValidationError("Add at least one fee line before saving.")


FeeStructureItemFormSet = inlineformset_factory(
    FeeStructure,
    FeeStructureItem,
    form=FeeStructureItemForm,
    formset=FeeStructureItemBaseFormSet,
    extra=1,
    can_delete=True,
)

# Explicit prefix so the JS in fee_structure_form.html (which targets
# #id_items-TOTAL_FORMS) matches regardless of Django's default naming.
FeeStructureItemFormSet.get_default_prefix = classmethod(lambda cls: "items")


# ============================================================
# BULK FEE CONFIGURATION
# ============================================================

class BulkFeeForm(forms.Form):
    """
    Form for bulk configuring fee structures across multiple programs and year levels.
    """
    programs = TradeMultipleChoiceField(
        queryset=Program.objects.filter(active=True).order_by("name"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Trades",
        required=True,
        help_text="Select the trades this fee applies to.",
    )

    year_levels = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Course years",
        required=True,
        help_text="Years beyond a trade's duration are skipped.",
    )

    fee_name = forms.CharField(
        max_length=100,
        label="Fee name",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. Tuition",
            "autocomplete": "off",
            "list": "fee-name-options",
        }),
        required=True,
        help_text="For example Tuition, Levy or Accommodation.",
    )

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        label="Amount per student",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "inputmode": "decimal",
            "placeholder": "0.00",
        }),
        required=True,
        help_text="Charged to every enrolled student in the selected trade and year.",
    )

    description = forms.CharField(
        max_length=255,
        required=False,
        label="Note (optional)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional note"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_years = _max_active_duration()
        self.fields["year_levels"].choices = [
            (str(level), f"Course year {level}") for level in range(1, max_years + 1)
        ]
        for field_name in ['programs', 'year_levels']:
            self.fields[field_name].widget.attrs.update({"class": "form-check-input"})

    def clean(self):
        cleaned_data = super().clean()
        programs = cleaned_data.get("programs", [])
        year_levels = cleaned_data.get("year_levels", [])

        if programs and year_levels:
            # Check if at least one trade/year combination is valid.
            valid_combinations = any(
                int(year_level) <= program.duration_years
                for program in programs
                for year_level in year_levels
            )

            if not valid_combinations:
                raise forms.ValidationError(
                    "None of the selected course years apply to the selected trades."
                )

        return cleaned_data


# ============================================================
# STUDENT
# ============================================================

class StudentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "student_number",
            "first_name",
            "national_id",
            "last_name",
            "date_of_birth",
            "gender",
            "guardian_name",
            "guardian_phone",
            'student_phone',
            "address",
            "program",
            "intake_year",
            "status",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"class": "form-control datepicker", "type": "text", "autocomplete": "off", "placeholder": "YYYY-MM-DD"},
                format="%Y-%m-%d",
            ),
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class StudentImportForm(BootstrapFormMixin, forms.Form):
    """
    Step 1 of the bulk student import: upload a spreadsheet and choose the
    intake year / starting semester / starting year level that will be
    applied to every student found in the file.
    """

    ALLOWED_EXTENSIONS = (".xlsx", ".csv")

    file = forms.FileField(
        label="Spreadsheet",
        help_text="Upload a .xlsx or .csv file with columns for student number, "
                   "surname, name and trade.",
    )

    intake_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by("-name"),
        label="Intake year",
        help_text="The academic year these students are starting in.",
    )

    semester = forms.ModelChoiceField(
        queryset=Semester.objects.none(),
        label="Starting semester",
        help_text="The semester these students will begin in (e.g. Semester 1).",
    )

    year_level = forms.ChoiceField(
        choices=[(i, str(i)) for i in range(1, 7)],
        initial=1,
        label="Starting year level",
    )

    default_status = forms.ChoiceField(
        choices=Student.STATUS_CHOICES,
        initial=Student.ACTIVE,
        label="Status to assign",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Narrow the semester choices to the chosen intake year once we know
        # it (works for both bound data and an already-set initial value).
        intake_year = None
        raw_intake_year = self.data.get("intake_year") if self.is_bound else None
        if raw_intake_year:
            intake_year = AcademicYear.objects.filter(pk=raw_intake_year).first()

        if intake_year:
            self.fields["semester"].queryset = Semester.objects.filter(
                academic_year=intake_year
            ).order_by("number")
        else:
            self.fields["semester"].queryset = Semester.objects.select_related(
                "academic_year"
            ).order_by("-academic_year__name", "number")

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        name = uploaded_file.name.lower()
        if not name.endswith(self.ALLOWED_EXTENSIONS):
            raise forms.ValidationError(
                "Please upload a .xlsx or .csv file."
            )
        return uploaded_file


class StudentStatusChangeForm(BootstrapFormMixin, forms.Form):
    """Used to change a student's status and log why (deferral, withdrawal, etc.)."""

    status = forms.ChoiceField(choices=Student.STATUS_CHOICES)
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text="e.g. 'Deferred due to fees', 'Withdrew - relocated'",
    )


# ============================================================
# ENROLLMENT
# ============================================================

class EnrollmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["student", "program", "semester", "year_level", "status"]


# ============================================================
# PAYMENT
# ============================================================

class PaymentForm(BootstrapFormMixin, forms.ModelForm):
    """Record one payment against one of the student's semesters.

    The semester queryset must be limited to the student's enrollments by the
    view. Receipt numbers are optional here: leaving the field blank makes the
    model allocate the next number for the payment date. Operators who use a
    pre-printed receipt book can still type their own number.
    """

    semester = forms.ModelChoiceField(
        queryset=Semester.objects.none(),
        required=True,
        error_messages={"required": "Choose the semester this payment is for."},
    )

    amount = forms.DecimalField(
        label="Amount received",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        error_messages={
            "required": "Enter the amount received.",
            "invalid": "Enter an amount like 150.00.",
            "min_value": "The amount must be more than zero.",
        },
    )

    method = forms.ChoiceField(
        label="Payment method",
        choices=Payment.PAYMENT_METHODS,
        initial=Payment.CASH,
        widget=forms.RadioSelect(),
    )

    payment_date = forms.DateField(
        label="Date received",
        error_messages={
            "required": "Enter the date the money was received.",
            "invalid": "Enter a valid date, for example 2026-10-30.",
        },
    )

    receipt_number = forms.CharField(
        label="Receipt number",
        required=False,
        max_length=50,
        help_text="Leave blank to use the next number in the receipt book.",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "spellcheck": "false",
                "placeholder": "Automatic",
            }
        ),
    )

    class Meta:
        model = Payment
        fields = [
            "semester",
            "receipt_number",
            "amount",
            "payment_date",
            "method",
            "reference",
            "notes",
        ]
        widgets = {
            "payment_date": forms.DateInput(
                attrs={
                    "class": "datepicker",
                    "type": "text",
                    "autocomplete": "off",
                    "placeholder": "YYYY-MM-DD",
                },
                format="%Y-%m-%d",
            ),
            "reference": forms.TextInput(
                attrs={"autocomplete": "off", "placeholder": "Bank slip or slip number"}
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Anything the next person should know"}
            ),
        }

    def __init__(self, *args, **kwargs):
        semester_queryset = kwargs.pop("semester_queryset", None)
        super().__init__(*args, **kwargs)

        if semester_queryset is not None:
            self.fields["semester"].queryset = semester_queryset

        # The radio inputs are styled as segments; drop the shared control class.
        self.fields["method"].widget.attrs.pop("class", None)

        if not self.is_bound:
            from school.utils.time_utils import get_current_date

            self.fields["payment_date"].initial = get_current_date()
            self.fields["method"].initial = Payment.CASH

    def clean_receipt_number(self):
        receipt = (self.cleaned_data.get("receipt_number") or "").strip()
        if not receipt:
            return ""

        clash = Payment.objects.filter(
            receipt_number__iexact=receipt
        ).exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError(
                "This receipt number has already been used. Leave it blank to "
                "use the next number in the book."
            )
        return receipt
