/**
 * admin-web — server-side session helper.
 *
 * Reads the admin JWT from the cookie, decodes claims.
 * Full verification happens in admin-svc; here we just extract role claims
 * for route gating.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export interface AdminSession {
  userId: string;
  roles: string[];
  email: string;
}

/**
 * Decode the admin JWT (server-side only, no verification — admin-svc verifies).
 * Returns null if cookie is missing or malformed.
 */
export async function decodeAdminSession(): Promise<AdminSession | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("colab-admin-session")?.value;
  if (!token) return null;

  try {
    const parts = token.split(".");
    const payloadB64 = parts[1];
    if (!payloadB64) return null;
    const payload = JSON.parse(
      Buffer.from(payloadB64, "base64url").toString("utf-8"),
    );
    return {
      userId: payload.sub ?? payload.user_id ?? "",
      roles: payload.roles ?? [],
      email: payload.email ?? "",
    };
  } catch {
    return null;
  }
}

/**
 * Require an admin session; redirect to /login if missing.
 */
export async function requireSession(): Promise<AdminSession> {
  const session = await decodeAdminSession();
  if (!session) {
    redirect("/login");
  }
  return session;
}

/**
 * Require one of the given roles; redirect to /forbidden if not present.
 */
export async function requireRole(roles: string[]): Promise<AdminSession> {
  const session = await requireSession();
  const hasRole = session.roles.some((r) => roles.includes(r));
  if (!hasRole) {
    redirect("/forbidden");
  }
  return session;
}
