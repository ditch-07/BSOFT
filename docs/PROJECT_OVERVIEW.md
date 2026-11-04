# Project Overview

BSOFT Student Management is a Django application for student administration,
semester enrollment, fee collection, reporting, and backups. Its user interface
is rendered by Django templates; it does not require a separate frontend or
asset build.

## Application structure

- `config/` — Django settings, root URL configuration, ASGI and WSGI entry
  points.
- `school/` — models, views, forms, JSON endpoints, reports, scheduler, and
  management commands.
- `templates/` — shared layouts and server-rendered pages.
- `static/` — application CSS, JavaScript, images, and vendor assets.
- `data/` — default SQLite database and backup data.
- `docs/` — project guides, capability references, and implementation history.

## Runtime

- Python 3.14 and Django 6.1
- SQLite
- WhiteNoise for static file serving
- APScheduler for automatic student progression
- openpyxl for spreadsheet import
- ReportLab for PDF reports

Runtime dependencies are listed in `requirements.txt`; development and
demo-data dependencies are listed in `requirements-dev.txt`.

## Start the application

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

By default, the database and backups are kept in `data/`. Set `BSOFT_DATA_DIR`
to select another writable location. See [DEPLOYMENT.md](./DEPLOYMENT.md) for
development and deployment checks, and [DJANGO_TEMPLATES.md](./DJANGO_TEMPLATES.md)
for the template interface conventions.

## Main application areas

- Student registration, editing, import, archive, and status history
- Academic years, semesters, programs, enrollments, and fee structures
- Payments, financial records, and audit history
- Operational reports with CSV and PDF exports
- User administration, database backups, and restore workflows
