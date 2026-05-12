/**
 * PostHog reverse-proxy via /ingest
 *
 * Routes /ingest/* to the PostHog host, stripping the /ingest prefix.
 * This prevents ad-blockers from blocking PostHog analytics.
 *
 * Pattern from PostHog docs: https://posthog.com/docs/advanced/proxy/nextjs
 *
 * NOTE: This route handler is NOT included in the static export (output: 'export').
 * Deployed as Lambda@Edge or proxied through gateway-svc.
 */

const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://app.posthog.com";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  return proxyToPostHog(req, await params);
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  return proxyToPostHog(req, await params);
}

async function proxyToPostHog(
  req: Request,
  params: { path: string[] }
): Promise<Response> {
  const path = params.path.join("/");
  const url = new URL(req.url);
  const targetUrl = `${POSTHOG_HOST}/${path}${url.search}`;

  const headers = new Headers(req.headers);
  headers.set("host", new URL(POSTHOG_HOST).host);

  try {
    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      ...(req.method !== "GET" && req.method !== "HEAD" && req.body != null
        ? { body: req.body }
        : {}),
    });

    return new Response(response.body, {
      status: response.status,
      headers: response.headers,
    });
  } catch {
    return Response.json({ error: "proxy_error" }, { status: 502 });
  }
}
