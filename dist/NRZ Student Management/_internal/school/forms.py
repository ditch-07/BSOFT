from django import forms
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
                attrs={"class": "form-control datepicker", "type": "text", "autocomplete": "off", "placeholder": "YYYY-MM-DD"},
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={"class": "form-control datepicker", "type": "text", "autocomplete": "off", "placeholder": "YYYY-MM-DD"},
                format="%Y-%m-%d",
            ),
        }


# ============================================================
# PROGRAM (replaces Course)
# ============================================================

class ProgramForm(BootstrapFormMixin, forms.ModelForm):
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

class FeeStructureForm(BootstrapFormMixin, forms.ModelForm):
    """
    Semester is NOT included here on purpose — it's always fixed by the
    URL (/semesters/<id>/fee-structures/new/) and set on the instance
    before the form is bound. Only Program + Year Level are chosen here.
    """

    class Meta:
        model = FeeStructure
        fields = ["program", "year_level"]


class FeeStructureItemForm(forms.ModelForm):
    class Meta:
        model = FeeStructureItem
        fields = ["name", "description", "amount"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Tuition"}
            ),
            "description": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Optional"}
            ),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
        }


FeeStructureItemFormSet = inlineformset_factory(
    FeeStructure,
    FeeStructureItem,
    form=FeeStructureItemForm,
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
    programs = forms.ModelMultipleChoiceField(
        queryset=Program.objects.filter(active=True),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=True,
        help_text="Select one or more programs to configure fees for.",
    )

    year_levels = forms.MultipleChoiceField(
        choices=[(i, str(i)) for i in range(1, 7)],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=True,
        help_text="Select year levels (1-6). Year levels exceeding a program's duration will be skipped.",
    )

    fee_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Tuition"}),
        required=True,
        help_text="Name of the fee item (e.g., Tuition, Levy, Accommodation).",
    )

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
        required=True,
        help_text="Amount for this fee item.",
    )

    description = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional description"}),
        help_text="Optional description for the fee item.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to checkbox fields
        for field_name in ['programs', 'year_levels']:
            self.fields[field_name].widget.attrs.update({"class": "form-check-input"})

    def clean(self):
        cleaned_data = super().clean()
        programs = cleaned_data.get("programs", [])
        year_levels = cleaned_data.get("year_levels", [])

        if programs and year_levels:
            # Check if at least one program/year_level combination is valid
            valid_combinations = False
            for program in programs:
                for year_level_str in year_levels:
                    year_level = int(year_level_str)
                    if year_level <= program.duration_years:
                        valid_combinations = True
                        break
                if valid_combinations:
                    break

            if not valid_combinations:
                raise forms.ValidationError(
                    "No valid program/year level combinations. Selected year levels exceed all selected programs' durations."
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
    """
    Semester field allows selecting which semester to pay for.
    The queryset should be filtered to the student's enrollments in the view.
    """
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.none(),
        required=True,
        empty_label="Select semester...",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Payment
        fields = [
            "semester",
            "receipt_number",
            "amount",
            "payment_date",
            "reference",
            "notes",
        ]
        widgets = {
            "payment_date": forms.DateInput(
                attrs={"class": "form-control datepicker", "type": "text", "autocomplete": "off", "placeholder": "YYYY-MM-DD"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        semester_queryset = kwargs.pop("semester_queryset", None)
        super().__init__(*args, **kwargs)
        if semester_queryset is not None:
            self.fields["semester"].queryset = semester_queryset
