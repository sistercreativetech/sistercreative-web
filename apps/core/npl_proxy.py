"""Proksi admin Ngaji Privat Lombok (NPL) lama ke webhook n8n.

Menggantikan Cloudflare Worker lama (legacy/src/index.js) dengan path yang sama,
supaya halaman admin NPL yang dibuat di n8n tetap berjalan tanpa perubahan:

  GET  /admin, /admin/                -> {N8N_BASE_URL}/webhook/npl-admin
  ANY  /admin/api, /admin/api/        -> {N8N_BASE_URL}/webhook/npl-admin-api
  ANY  /webhook/npl-admin-api         -> {N8N_BASE_URL}/webhook/npl-admin-api (jalur cadangan)

Django admin bawaan TIDAK di /admin (lihat DJANGO_ADMIN_URL), jadi tidak bentrok.
"""

import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
FORWARDED_REQUEST_HEADERS = ("Content-Type", "Authorization", "Accept")
DROPPED_RESPONSE_HEADERS = {
    "content-security-policy",
    "content-security-policy-report-only",
    "x-frame-options",
    "content-length",
    "transfer-encoding",
    "connection",
    "content-encoding",
}


@method_decorator(csrf_exempt, name="dispatch")
class NplProxyView(View):
    webhook = "npl-admin-api"
    allowed_methods = ("GET", "POST")
    http_method_names = ["get", "post", "options"]

    def options(self, request, *args, **kwargs):
        response = HttpResponse(status=204)
        return self._cors(response)

    def get(self, request):
        return self._proxy(request)

    def post(self, request):
        return self._proxy(request)

    def _cors(self, response):
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    def _proxy(self, request):
        base = settings.N8N_BASE_URL.rstrip("/")
        if not base:
            return JsonResponse(
                {"ok": False, "message": "Layanan admin belum dikonfigurasi."}, status=503
            )
        url = f"{base}/webhook/{self.webhook}"
        query = request.META.get("QUERY_STRING", "")
        if query:
            url = f"{url}?{query}"

        data = request.body if request.method == "POST" else None
        upstream = urllib.request.Request(url, data=data, method=request.method)  # noqa: S310
        for header in FORWARDED_REQUEST_HEADERS:
            value = request.headers.get(header)
            if value:
                upstream.add_header(header, value)

        try:
            with urllib.request.urlopen(upstream, timeout=TIMEOUT_SECONDS) as remote:  # noqa: S310
                status, headers, body = remote.status, remote.headers, remote.read()
        except urllib.error.HTTPError as exc:
            status, headers, body = exc.code, exc.headers, exc.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("Proksi NPL gagal: %s", exc)
            return self._cors(
                JsonResponse({"ok": False, "message": "Terjadi kesalahan pada server."}, status=502)
            )

        response = HttpResponse(body, status=status)
        for name, value in headers.items():
            if name.lower() not in DROPPED_RESPONSE_HEADERS:
                response[name] = value
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        # Halaman admin NPL dibuat di n8n dan boleh tampil apa adanya di domain ini.
        response.xframe_options_exempt = True
        return self._cors(response)


class NplAdminPageView(NplProxyView):
    webhook = "npl-admin"
    http_method_names = ["get", "options"]
