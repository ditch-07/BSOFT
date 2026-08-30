from django.contrib import admin

from .models import (
    AcademicYear,
    Semester,
    Program,
    FeeStructure,
    FeeStructureItem,
    Student,
    StudentStatusLog,
    Enrollment,
    StudentCharge,
    Payment,
)

admin.site.register(AcademicYear)
admin.site.register(Semester)
admin.site.register(Program)
admin.site.register(FeeStructure)
admin.site.register(FeeStructureItem)
admin.site.register(Student)
admin.site.register(StudentStatusLog)
admin.site.register(Enrollment)
admin.site.register(StudentCharge)
admin.site.register(Payment)