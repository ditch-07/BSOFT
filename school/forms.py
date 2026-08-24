from django import forms
from django.forms import inlineformset_factory

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
                widget.attrs["class"] = "form-select"
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            else:
                widget.attrs["class"] = "form-control"


# ============================================================
# ACADEMIC YEAR / SEMESTER
# ============================================================

class AcademicYearForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "is_current"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class SemesterForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Semester
        fields = ["academic_year", "number", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


# ============================================================
# PROGRAM (replaces Course)
# ============================================================

class ProgramForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Program
        fields = ["code", "name", "description", "duration_years", "active"]
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
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
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
    Semester is deliberately excluded — payment_create() always derives it
    from the student's active enrollment and sets it on the instance
    before saving, so it should never be a field the admin picks by hand.
    """

    class Meta:
        model = Payment
        fields = [
            "receipt_number",
            "amount",
            "payment_date",
            "method",
            "reference",
            "notes",
        ]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
