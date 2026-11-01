from django.contrib import admin
from django.conf import settings
from django.urls import include, path, re_path
from config.views import nuxt_app

handler403 = "config.views.api_permission_denied"

urlpatterns = [path("admin/", admin.site.urls)]

if settings.FRONTEND_MODE == "vue":
    urlpatterns.extend([
        path("", nuxt_app, name="vue_home"),
        re_path(r"^(?!api/|admin/|static/|media/).+$", nuxt_app, name="vue_page"),
    ])

urlpatterns.append(path("", include("school.urls")))