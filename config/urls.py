from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView


urlpatterns = [

    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "",
        include("school.urls"),
    ),

    # Catch-all for Nuxt SPA - must be last
    re_path(r'^(?!api/|admin/|static/|media/).*/?$', TemplateView.as_view(template_name='spa.html')),
]