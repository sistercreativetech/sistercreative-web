const N8N_BASE_URL =
  "https://n8n-7ctg.srv1967964.hstgr.cloud";

const ADMIN_WEBHOOK =
  N8N_BASE_URL + "/webhook/npl-admin";

const API_WEBHOOK =
  N8N_BASE_URL + "/webhook/npl-admin-api";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    try {
      /*
       * Menampilkan halaman Admin NPL
       * Alamat:
       * https://sistercreative.tech/admin
       */
      if (
        request.method === "GET" &&
        (path === "/admin" || path === "/admin/")
      ) {
        return await proxyToN8n(
          request,
          ADMIN_WEBHOOK + url.search
        );
      }

      /*
       * API login dan pengambilan data
       * Alamat:
       * https://sistercreative.tech/admin/api
       */
      if (
        path === "/admin/api" ||
        path === "/admin/api/"
      ) {
        return await proxyToN8n(
          request,
          API_WEBHOOK + url.search
        );
      }

      /*
       * Jalur cadangan untuk kode HTML lama.
       * Tetap diarahkan ke webhook API n8n.
       */
      if (
        path === "/webhook/npl-admin-api" ||
        path === "/webhook/npl-admin-api/"
      ) {
        return await proxyToN8n(
          request,
          API_WEBHOOK + url.search
        );
      }

      /*
       * Menampilkan website utama dari folder public.
       */
      return await env.ASSETS.fetch(request);
    } catch (error) {
      return jsonResponse(
        {
          ok: false,
          message: "Terjadi kesalahan pada server.",
          error: error.message
        },
        500
      );
    }
  }
};

async function proxyToN8n(originalRequest, targetUrl) {
  const headers = new Headers(originalRequest.headers);

  /*
   * Header Host akan dibuat otomatis oleh Cloudflare.
   */
  headers.delete("host");
  headers.delete("content-length");

  const options = {
    method: originalRequest.method,
    headers: headers,
    redirect: "follow"
  };

  /*
   * GET dan HEAD tidak boleh memiliki body.
   */
  if (
    originalRequest.method !== "GET" &&
    originalRequest.method !== "HEAD"
  ) {
    options.body = originalRequest.body;
  }

  const n8nResponse = await fetch(targetUrl, options);

  const responseHeaders = new Headers(
    n8nResponse.headers
  );

  /*
   * Mengizinkan halaman ditampilkan langsung
   * melalui domain sistercreative.tech.
   */
  responseHeaders.delete("content-security-policy");
  responseHeaders.delete(
    "content-security-policy-report-only"
  );
  responseHeaders.delete("x-frame-options");

  responseHeaders.set(
    "Access-Control-Allow-Origin",
    "*"
  );

  responseHeaders.set(
    "Access-Control-Allow-Methods",
    "GET, POST, OPTIONS"
  );

  responseHeaders.set(
    "Access-Control-Allow-Headers",
    "Content-Type, Authorization"
  );

  responseHeaders.set(
    "Cache-Control",
    "no-store, no-cache, must-revalidate"
  );

  return new Response(n8nResponse.body, {
    status: n8nResponse.status,
    statusText: n8nResponse.statusText,
    headers: responseHeaders
  });
}

function jsonResponse(data, status) {
  return new Response(JSON.stringify(data), {
    status: status,
    headers: {
      "Content-Type": "application/json; charset=UTF-8",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*"
    }
  });
}
