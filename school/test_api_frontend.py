import json

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import Client, TestCase
from django.urls import resolve

from config.views import nuxt_app


class FrontendApiIntegrationTests(TestCase):
    def test_vue_routes_use_the_spa_and_api_routes_remain_available(self):
        if settings.FRONTEND_MODE == "vue":
            self.assertIs(resolve("/").func, nuxt_app)
            self.assertIs(resolve("/students/").func, nuxt_app)
        else:
            self.assertEqual(resolve("/").url_name, "dashboard")
            self.assertEqual(resolve("/students/").url_name, "student_list")
        self.assertEqual(resolve("/api/dashboard/").url_name, "api_dashboard")

    def test_unauthenticated_api_requests_return_json_401(self):
        response = self.client.get("/api/dashboard/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Authentication credentials were not provided.")

    def test_auth_check_sets_csrf_cookie_and_student_search_is_available(self):
        response = self.client.get("/api/auth/check/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

        user = get_user_model().objects.create_superuser(
            username="api-reader",
            email="api-reader@example.com",
            password="test-password",
        )
        self.client.force_login(user)
        response = self.client.get("/api/students/search/?q=ad")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"students": []})

    def test_api_logout_requires_csrf_token(self):
        user = get_user_model().objects.create_user(
            username="api-user",
            password="test-password",
        )
        client = Client(enforce_csrf_checks=True)
        client.get("/api/auth/check/")
        csrf_token = client.cookies["csrftoken"].value
        login_response = client.post(
            "/api/auth/login/",
            data=json.dumps({"username": user.username, "password": "test-password"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200)

        rejected = client.post(
            "/api/auth/logout/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 403)

        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            "/api/auth/logout/",
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
