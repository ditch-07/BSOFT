# Static Assets — Flatpickr (v4.6.13)

Pulled straight from npm so nothing depends on jsdelivr / any CDN. Works fully offline once these files are in your project.

## 1. Place the files

Copy the `vendor/flatpickr/` folder into wherever your app's static files live, e.g.:

```
yourapp/static/vendor/flatpickr/flatpickr.min.css
yourapp/static/vendor/flatpickr/flatpickr.min.js
```

If you're using a project-level static dir instead (`STATICFILES_DIRS` in settings.py), drop it there instead — same folder structure.

## 2. Reference it in base.html

Replace the CDN `<link>`/`<script>` tags from before with:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'vendor/flatpickr/flatpickr.min.css' %}">
<script src="{% static 'vendor/flatpickr/flatpickr.min.js' %}"></script>
```

Everything else (the `flatpickr(".datepicker", {...})` init script, the `.form-control.datepicker` class, the forms.py widget) stays exactly as given earlier — only the two `<link>`/`<script>` source URLs change.

## Collect static assets

Run the usual:

```bash
python manage.py collectstatic
```

Collected files are written to `staticfiles/`; WhiteNoise is already configured
in the Django settings to serve static assets.

## Updating Flatpickr

Flatpickr is stable and rarely needs updates. When you do want a newer version, just re-download `dist/flatpickr.min.js` + `dist/flatpickr.min.css` from a fresh `npm install flatpickr` and overwrite these two files — nothing else changes.
