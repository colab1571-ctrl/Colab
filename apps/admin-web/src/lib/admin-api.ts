/**
 * admin-web — typed client for admin-svc API.
 *
 * All calls are server-side (from Server Components or Server Actions),
 * using the service-to-service JWT so the browser never holds admin credentials.
 */

const ADMIN_API_BASE =
  process.env.ADMIN_API_BASE_URL ?? "http://admin-svc:8000";

type FetchOptions = {
  method?: string;
  body?: unknown;
  adminUserId: string;
  adminRoles: string[];
  mfaStepup?: boolean;
};

async function adminFetch<T>(
  path: string,
  opts: FetchOptions,
  revalidate = 0,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Service-Auth": "admin-web",
    "X-Admin-User-Id": opts.adminUserId,
    "X-Admin-Roles": opts.adminRoles.join(","),
  };
  if (opts.mfaStepup) {
    headers["X-Mfa-Stepup"] = "true";
  }

  const res = await fetch(`${ADMIN_API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    ...(opts.body != null ? { body: JSON.stringify(opts.body) } : {}),
    next: { revalidate },
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`admin-svc ${opts.method ?? "GET"} ${path} → ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Moderation
// ---------------------------------------------------------------------------

export interface CaseSummary {
  id: string;
  subject_type: string;
  priority_tier: string;
  score: number;
  sla_due_at: string;
  status: string;
  opened_at: string;
}

export async function getModerationQueue(
  adminUserId: string,
  adminRoles: string[],
  params?: Record<string, string>,
): Promise<CaseSummary[]> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return adminFetch<CaseSummary[]>(`/admin/v1/queue/moderation${qs}`, {
    adminUserId,
    adminRoles,
  });
}

export async function getCaseDetail(
  id: string,
  adminUserId: string,
  adminRoles: string[],
): Promise<unknown> {
  return adminFetch<unknown>(`/admin/v1/cases/${id}`, { adminUserId, adminRoles });
}

export async function takeCaseAction(
  id: string,
  action: { action_type: string; reason: string },
  adminUserId: string,
  adminRoles: string[],
): Promise<unknown> {
  return adminFetch<unknown>(`/admin/v1/cases/${id}/action`, {
    method: "POST",
    body: action,
    adminUserId,
    adminRoles,
  });
}

// ---------------------------------------------------------------------------
// Support
// ---------------------------------------------------------------------------

export async function getSupportQueue(
  adminUserId: string,
  adminRoles: string[],
  params?: Record<string, string>,
): Promise<unknown[]> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return adminFetch<unknown[]>(`/admin/v1/queue/support${qs}`, {
    adminUserId,
    adminRoles,
  });
}

export async function getTicketDetail(
  id: string,
  adminUserId: string,
  adminRoles: string[],
): Promise<unknown> {
  return adminFetch<unknown>(`/admin/v1/tickets/${id}`, { adminUserId, adminRoles });
}

export async function replyToTicket(
  id: string,
  body: string,
  adminUserId: string,
  adminRoles: string[],
): Promise<unknown> {
  return adminFetch<unknown>(`/admin/v1/tickets/${id}/reply`, {
    method: "POST",
    body: { body },
    adminUserId,
    adminRoles,
  });
}

// ---------------------------------------------------------------------------
// Billing
// ---------------------------------------------------------------------------

export async function getTiers(
  adminUserId: string,
  adminRoles: string[],
): Promise<Record<string, Record<string, unknown>>> {
  return adminFetch<Record<string, Record<string, unknown>>>("/admin/v1/tiers", {
    adminUserId,
    adminRoles,
    revalidate: 300,
  } as FetchOptions & { revalidate?: number }, 300);
}

export async function getRefunds(
  adminUserId: string,
  adminRoles: string[],
  status = "pending",
): Promise<unknown[]> {
  return adminFetch<unknown[]>(`/admin/v1/refunds?status=${status}`, {
    adminUserId,
    adminRoles,
  });
}

export async function decideRefund(
  id: string,
  decision: { decision: string; reason: string; amount?: number },
  adminUserId: string,
  adminRoles: string[],
): Promise<unknown> {
  return adminFetch<unknown>(`/admin/v1/refunds/${id}/decision`, {
    method: "POST",
    body: decision,
    adminUserId,
    adminRoles,
  });
}

export async function grantCredits(
  payload: { user_id: string; delta_cents: number; reason: string },
  adminUserId: string,
  adminRoles: string[],
): Promise<unknown> {
  return adminFetch<unknown>("/admin/v1/credits/grant", {
    method: "POST",
    body: payload,
    adminUserId,
    adminRoles,
  });
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export async function getUser360(
  id: string,
  adminUserId: string,
  adminRoles: string[],
  reveal = false,
): Promise<unknown> {
  return adminFetch<unknown>(`/admin/v1/users/${id}/360?reveal=${reveal}`, {
    adminUserId,
    adminRoles,
  });
}

// ---------------------------------------------------------------------------
// Feature flags
// ---------------------------------------------------------------------------

export interface FeatureFlag {
  key: string;
  env: string;
  value: unknown;
  canary_pct: number;
  description: string;
  updated_by: string;
  updated_at: string;
}

export async function getFlags(
  adminUserId: string,
  adminRoles: string[],
  env?: string,
): Promise<FeatureFlag[]> {
  const qs = env ? `?env=${env}` : "";
  return adminFetch<FeatureFlag[]>(`/admin/v1/flags${qs}`, {
    adminUserId,
    adminRoles,
    revalidate: 60,
  } as FetchOptions & { revalidate?: number }, 60);
}

export async function upsertFlag(
  flag: Partial<FeatureFlag>,
  adminUserId: string,
  adminRoles: string[],
  mfaStepup = false,
): Promise<FeatureFlag> {
  return adminFetch<FeatureFlag>("/admin/v1/flags", {
    method: "PUT",
    body: flag,
    adminUserId,
    adminRoles,
    mfaStepup,
  });
}

// ---------------------------------------------------------------------------
// KPI rollups
// ---------------------------------------------------------------------------

export interface KPIRollupRow {
  day: string;
  key: string;
  dims: Record<string, string>;
  value: number | null;
  count_n: number | null;
}

export async function getKpiRollups(
  adminUserId: string,
  adminRoles: string[],
  params?: { key?: string; from?: string; to?: string },
): Promise<KPIRollupRow[]> {
  const qs = params ? "?" + new URLSearchParams(params as Record<string, string>).toString() : "";
  return adminFetch<KPIRollupRow[]>(`/admin/v1/kpi/rollups${qs}`, {
    adminUserId,
    adminRoles,
  });
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export async function getAuditLog(
  adminUserId: string,
  adminRoles: string[],
  params?: Record<string, string>,
): Promise<unknown[]> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return adminFetch<unknown[]>(`/admin/v1/audit${qs}`, {
    adminUserId,
    adminRoles,
  });
}
