from django.contrib import admin

from .models import (
    AcademicYear,
    Semester,
    FeeItem,
    SemesterFee,
    Student,
    StudentCharge,
    Payment,
)


admin.site.register(AcademicYear)
admin.site.register(Semester)
admin.site.register(FeeItem)
admin.site.register(SemesterFee)
admin.site.register(Student)
admin.site.register(StudentCharge)
admin.site.register(Payment)