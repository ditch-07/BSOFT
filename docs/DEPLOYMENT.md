# Development and Deployment

BSOFT is a Django application rendered with Django templates. The supported
entry point is `manage.py`; there is no separate frontend build or installer.

## Local setup

1. Create and activate a Python virtual environment.
2. Install runtime dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Apply database migrations and start Django:

   ```powershell
   python manage.py migrate
   python manage.py runserver
   ```

4. Open `http://127.0.0.1:8000/` and sign in.

The SQLite database and generated backups are stored under `data/` by default.
Set `BSOFT_DATA_DIR` to use another writable directory. `DJANGO_SECRET_KEY`
may be set explicitly; otherwise Django creates and persists a key in the data
directory.

## Static assets

Application assets live in `static/` and templates live in `templates/`.
For a deployment that collects static files, run:

```powershell
python manage.py collectstatic --noinput
```

Set `DJANGO_DEBUG=0` and configure `DJANGO_ALLOWED_HOSTS` for non-local
deployments. Use a properly secured production web server and HTTPS when
serving the application beyond the local machine.

## Checks and tests

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test school
```

Set `BSOFT_DISABLE_SCHEDULER=1` when running checks or tests that should not
start the background progression scheduler.
