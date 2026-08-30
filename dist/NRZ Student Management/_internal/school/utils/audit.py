from school.models import AuditLog


def log_action(user, action, student=None, summary='', details=None, category='STUDENT'):
    """Helper to create an audit log entry."""
    AuditLog.objects.create(
        user=user,
        action=action,
        student=student,
        summary=summary,
        details=details or {},
        category=category,
    )