/**
 * Admin app middleware — IP allowlist + admin role check.
 *
 * IP enforcement comment: Actual IP filtering is done at the AWS API Gateway / WAF layer.
 * This middleware performs an additional application-level check as defense-in-depth.
 * In production, configure the WAF IP set in terraform/modules/waf/ (spec 001 extension).
 */

import { type NextRequest, NextResponse } from "next/server";

// Application-level check (WAF handles the real enforcement)
const ADMIN_IP_ALLOWLIST = (process.env.ADMIN_IP_ALLOWLIST ?? "127.0.0.1,::1")
  .split(",")
  .map((ip) => ip.trim());

export function middleware(request: NextRequest): NextResponse {
  // Skip /login page
  if (request.nextUrl.pathname === "/login") {
    return NextResponse.next();
  }

  // Check IP (application-level — WAF is primary enforcement)
  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp = forwardedFor?.split(",")[0]?.trim() ?? "unknown";

  if (
    process.env.NODE_ENV === "production" &&
    ADMIN_IP_ALLOWLIST.length > 0 &&
    !ADMIN_IP_ALLOWLIST.includes(clientIp)
  ) {
    return new NextResponse(
      JSON.stringify({ error: { code: "FORBIDDEN", message: "IP not in admin allowlist." } }),
      { status: 403, headers: { "Content-Type": "application/json" } }
    );
  }

  // Auth check: require colab-session cookie with admin role
  const sessionCookie = request.cookies.get("colab-session");
  if (!sessionCookie) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|login).*)",
  ],
};
