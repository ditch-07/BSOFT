# Django Template Interface

The application UI is rendered by Django. Page templates are in
`templates/school/`, with shared layouts in `templates/base.html` and
`templates/base_login.html`. Static CSS, JavaScript, images, and vendor assets
are served from `static/`.

## Run locally

From the repository root:

```powershell
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Django handles both page rendering and the
same-origin JSON endpoints under `/api/`; no JavaScript frontend server or
asset-generation step is required.

## Template conventions

- Extend `base.html` for authenticated application pages and
  `base_login.html` for authentication pages.
- Use Django's `{% url %}` tag for internal links and `{% static %}` for static
  assets.
- Keep authorization and business rules in Django views and model/service
  code; templates should only render the supplied context.
