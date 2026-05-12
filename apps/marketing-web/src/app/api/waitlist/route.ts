/**
 * POST /api/waitlist
 *
 * Waitlist email capture endpoint.
 * - Validates email + source with zod
 * - Hashes IP (SHA-256, one-way, stored for duplicate detection)
 * - Creates SES contact (stub — SES client wired, WAITLIST_LIST_NAME env var required)
 * - Persists WaitlistEmail row via DB (stub — DATABASE_URL env var required)
 * - Returns { ok: true } | structured error
 *
 * Rate limiting is handled at the API Gateway / CloudFront layer (5 req/IP/hr).
 *
 * NOTE: This route handler is NOT included in the static export (output: 'export').
 * It must be deployed as a Lambda@Edge function or proxied through gateway-svc.
 * See plan §2.1 and §6 for infrastructure decision context.
 */

import { z } from "zod";
import { SESv2Client, CreateContactCommand } from "@aws-sdk/client-sesv2";

// ---------------------------------------------------------------------------
// Validation schema
// ---------------------------------------------------------------------------

const schema = z.object({
  email: z.string().email().max(254),
  source: z.string().max(64).default("homepage"),
  consentAt: z.string().datetime().optional(), // CASL — Canadian visitors
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function hashIp(raw: string): Promise<string> {
  const data = new TextEncoder().encode(raw);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function POST(req: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return Response.json(
      { error: "invalid_input", details: parsed.error.flatten() },
      { status: 422 }
    );
  }

  const { email, source, consentAt } = parsed.data;

  // Hash IP for duplicate-detection and CASL records
  const ipRaw = req.headers.get("x-forwarded-for") ?? "unknown";
  const ipHashed = await hashIp(ipRaw.split(",")[0].trim());

  // ---------------------------------------------------------------------------
  // 1. SES: add contact to waitlist list
  // ---------------------------------------------------------------------------
  const listName = process.env.WAITLIST_LIST_NAME;
  const region = process.env.AWS_REGION ?? "us-east-1";

  if (listName) {
    try {
      const ses = new SESv2Client({ region });
      await ses.send(
        new CreateContactCommand({
          ContactListName: listName,
          EmailAddress: email,
          TopicPreferences: [
            { TopicName: "waitlist", SubscriptionStatus: "OPT_IN" },
          ],
        })
      );
    } catch (err: unknown) {
      // SES throws if contact already exists in the list — treat as duplicate
      const errCode = (err as { name?: string })?.name;
      if (errCode === "AlreadyExistsException") {
        return Response.json({ error: "already_on_waitlist" }, { status: 409 });
      }
      console.error("[waitlist] SES error:", err);
      return Response.json({ error: "service_unavailable" }, { status: 503 });
    }
  } else {
    // Dev / CI fallback — log and continue without SES
    console.log("[waitlist] WAITLIST_LIST_NAME not set; skipping SES:", {
      email,
      source,
    });
  }

  // ---------------------------------------------------------------------------
  // 2. Persist WaitlistEmail row
  //    Deferred: direct DB write requires DATABASE_URL and a DB client.
  //    In production this call is proxied through gateway-svc -> notification-svc.
  //    For now, log the record; infrastructure team wires the DB call.
  // ---------------------------------------------------------------------------
  const dbUrl = process.env.DATABASE_URL;
  if (dbUrl) {
    // TODO(infra): replace with actual DB insert via gateway-svc internal API
    // INSERT INTO waitlist_emails (email, source, consent_at, ip_hashed)
    // VALUES ($1, $2, $3, $4) ON CONFLICT (email) DO NOTHING RETURNING id
    console.log("[waitlist] DB stub — would insert:", {
      email,
      source,
      consent_at: consentAt ?? null,
      ip_hashed: ipHashed,
    });
  }

  // ---------------------------------------------------------------------------
  // 3. Confirmation email (deferred to infra / notification-svc integration)
  // ---------------------------------------------------------------------------
  // TODO(spec-017): send SES template 'waitlist-confirm' via notification-svc

  return Response.json({ ok: true }, { status: 201 });
}
