# NRZ Student Management frontend

The Nuxt/Vue application is the default web interface. It reads and changes
application data through Django's session-authenticated JSON API; the generated
Nuxt files contain the app shell and assets, not a copy of school data.

## Development

Start Django from the repository root:

```powershell
python manage.py migrate
python manage.py runserver
```

In another terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Nuxt proxies `/api` requests to Django on port 8000
and uses the same browser session for API requests.

## Serve Vue through Django

Generate the client app before starting Django:

```powershell
Set-Location frontend
npm run generate
Set-Location ..
python manage.py collectstatic --noinput
python manage.py runserver
```

The generated entry document is served by Django and its assets are exposed
through Django static files. All student, payment, report, and administration
data continues to load from `/api/` at runtime.

## Switch back to Django templates

Set `NRZ_FRONTEND_MODE` before starting Django:

```powershell
$env:NRZ_FRONTEND_MODE = "django"
python manage.py runserver
```

Unset it or set it to `vue` to use the Vue app again. Restart Django after
changing the setting.
