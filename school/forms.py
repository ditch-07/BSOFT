from django import forms
from django.forms import inlineformset_factory
from .models import (
    AcademicYear,
    Semester,
    Course,
    SemesterFee,
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


class AcademicYearForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "is_current"]

class SemesterForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Semester
        fields = [
            "academic_year",
            "number",
            "start_month",
            "end_month",
        ]

class CourseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "name", "description", "active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


# --- NEW: Simple SemesterFee form with name and amount ---
class SemesterFeeForm(forms.ModelForm):
    class Meta:
        model = SemesterFee
        fields = ["name", "amount"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Tuition"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


# --- Only ONE correct formset definition ---
SemesterFeeFormSet = inlineformset_factory(
    Semester,
    SemesterFee,
    form=SemesterFeeForm,
    extra=1,
    can_delete=True,
)


class StudentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "student_number",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "guardian_name",
            "guardian_phone",
            "address",
            "active",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class EnrollmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["student", "course", "semester", "status"]


class PaymentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            "receipt_number",
            "semester",
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