import io
import urllib.error
from email.message import Message
from unittest import mock

from django.test import TestCase, override_settings

N8N = "https://n8n.contoh.test"


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"", status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@override_settings(N8N_BASE_URL=N8N)
class NplProxyTests(TestCase):
    def test_admin_page_proxies_to_n8n_and_allows_framing(self):
        html = b"<html><body>Admin NPL</body></html>"
        upstream = FakeResponse(
            html,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Content-Security-Policy": "frame-ancestors 'none'",
                "X-Frame-Options": "DENY",
            },
        )
        with mock.patch("urllib.request.urlopen", return_value=upstream) as urlopen:
            response = self.client.get("/admin?tab=murid")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, f"{N8N}/webhook/npl-admin?tab=murid")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, html)
        self.assertNotIn("Content-Security-Policy", response)
        self.assertNotIn("X-Frame-Options", response)
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")

    def test_api_post_forwards_body_without_csrf(self):
        upstream = FakeResponse(b'{"ok":true}', headers={"Content-Type": "application/json"})
        client = self.client_class(enforce_csrf_checks=True)
        with mock.patch("urllib.request.urlopen", return_value=upstream) as urlopen:
            response = client.post("/admin/api", b'{"pin":"1234"}', content_type="application/json")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, f"{N8N}/webhook/npl-admin-api")
        self.assertEqual(request.data, b'{"pin":"1234"}')
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(response.json(), {"ok": True})

    def test_legacy_webhook_path_and_slash_variants(self):
        for path in ["/admin/", "/admin/api/", "/webhook/npl-admin-api", "/npl-admin/"]:
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"ok")):
                self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_upstream_http_error_is_passed_through(self):
        error = urllib.error.HTTPError(
            f"{N8N}/webhook/npl-admin-api", 401, "Unauthorized", Message(), io.BytesIO(b"PIN salah")
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            response = self.client.post("/admin/api", b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"PIN salah")

    def test_upstream_down_returns_502(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            response = self.client.get("/admin/api")
        self.assertEqual(response.status_code, 502)

    def test_options_preflight(self):
        response = self.client.options("/admin/api")
        self.assertEqual(response.status_code, 204)
        self.assertIn("POST", response["Access-Control-Allow-Methods"])

    def test_admin_page_rejects_post(self):
        self.assertEqual(self.client.post("/admin/").status_code, 405)

    @override_settings(N8N_BASE_URL="")
    def test_not_configured(self):
        self.assertEqual(self.client.get("/admin/").status_code, 503)


class ProductionSettingsTests(TestCase):
    def test_prod_settings_import_with_env(self):
        import importlib
        import os

        env = {
            "DJANGO_SECRET_KEY": "x" * 50,
            "POSTGRES_DB": "db",
            "POSTGRES_USER": "u",
            "POSTGRES_PASSWORD": "p",
        }
        with mock.patch.dict(os.environ, env):
            prod = importlib.import_module("config.settings.prod")
            prod = importlib.reload(prod)
        self.assertFalse(prod.DEBUG)
        self.assertEqual(prod.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertIn(r"^healthz/$", prod.SECURE_REDIRECT_EXEMPT)
