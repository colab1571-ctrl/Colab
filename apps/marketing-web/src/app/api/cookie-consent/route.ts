/**
 * POST /api/cookie-consent
 *
 * Anonymous cookie consent audit log endpoint.
 * Records the consent event server-side (not linked to any user identity).
 * Used for compliance auditing only.
 *
 * Body: { consentRecord: { consentVersion, categories, acceptedAt } }
 *
 * NOTE: This route handler is NOT included in the static export (output: 'export').
 * Deployed as Lambda@Edge or proxied through gateway-svc.
 */

import { z } from "zod";

const schema = z.object({
  consentRecord: z.object({
    consentVersion: z.string().max(16),
    categories: z.array(z.string().max(32)),
    acceptedAt: z.string().datetime(),
  }),
});

export async function POST(req: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "invalid_input" }, { status: 422 });
  }

  const { consentRecord } = parsed.data;

  // Anonymised IP hash for basic dedup (not linked to user identity)
  const ipRaw = req.headers.get("x-forwarded-for") ?? "unknown";
  const ipData = new TextEncoder().encode(ipRaw.split(",")[0].trim());
  const ipHash = await crypto.subtle.digest("SHA-256", ipData);
  const ipHashHex = Array.from(new Uint8Array(ipHash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Audit log entry — in production, write to a structured log or append-only table
  // For now: structured console output (CloudWatch ingests this)
  console.log(
    JSON.stringify({
      event: "cookie_consent_accepted",
      consentVersion: consentRecord.consentVersion,
      categories: consentRecord.categories,
      acceptedAt: consentRecord.acceptedAt,
      ipHash: ipHashHex,
      ts: new Date().toISOString(),
    })
  );

  return Response.json({ ok: true }, { status: 200 });
}
