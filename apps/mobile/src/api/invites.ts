/**
 * Invites API client — typed wrappers for invite-svc REST endpoints.
 *
 * Endpoints:
 *   POST   /invites
 *   POST   /invites/{id}/accept
 *   POST   /invites/{id}/reject
 *   DELETE /invites/{id}
 *   GET    /invites/inbox
 *   GET    /invites/sent
 *   POST   /blocks/{profile_id}
 *   DELETE /blocks/{profile_id}
 *   GET    /blocks
 */

import { useAuthStore } from "../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProfileCard {
  profile_id: string;
  display_name: string | null;
  avatar_url: string | null;
  city: string | null;
  top_vocation: string | null;
}

export interface InviteCard {
  invite_id: string;
  from_profile: ProfileCard | null;
  to_profile: ProfileCard | null;
  synopsis: string;
  status: "pending" | "accepted" | "rejected" | "expired" | "cancelled";
  created_at: string;
  archive_at: string;
  ai_match_score: number | null;
  responded_at: string | null;
}

export interface InviteListResponse {
  items: InviteCard[];
  next_cursor: string | null;
  total_pending: number;
}

export interface SendVibeCheckParams {
  toProfileId: string;
  synopsis: string;
  idempotencyKey?: string;
}

export interface SendVibeCheckResponse {
  invite_id: string;
  status: "pending";
  quota_remaining: number;
  archive_at: string;
}

export interface AcceptResponse {
  invite_id: string;
  status: "accepted";
  matched: boolean;
}

export interface BlockCard {
  profile_id: string;
  display_name: string | null;
  avatar_url: string | null;
  blocked_at: string;
}

export interface BlockListResponse {
  items: BlockCard[];
  next_cursor: string | null;
}

export interface BlockResponse {
  blocker_id: string;
  blocked_id: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`API error ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function authFetch(
  path: string,
  options: RequestInit & { idempotencyKey?: string } = {}
): Promise<Response> {
  const { accessToken } = useAuthStore.getState();
  const { idempotencyKey, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  if (idempotencyKey) {
    headers["X-Idempotency-Key"] = idempotencyKey;
  }

  const resp = await fetch(`${BASE_URL}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (!resp.ok) {
    let body: unknown;
    try {
      body = await resp.json();
    } catch {
      body = null;
    }
    throw new ApiError(resp.status, body);
  }

  return resp;
}

// ---------------------------------------------------------------------------
// Invite endpoints
// ---------------------------------------------------------------------------

export async function sendVibeCheck(
  params: SendVibeCheckParams
): Promise<SendVibeCheckResponse> {
  const resp = await authFetch("/invites", {
    method: "POST",
    body: JSON.stringify({
      to_profile_id: params.toProfileId,
      synopsis: params.synopsis,
    }),
    idempotencyKey: params.idempotencyKey,
  });
  return resp.json() as Promise<SendVibeCheckResponse>;
}

export async function respondToInvite(
  inviteId: string,
  action: "accept" | "reject"
): Promise<AcceptResponse | { invite_id: string; status: "rejected" }> {
  const resp = await authFetch(`/invites/${inviteId}/${action}`, {
    method: "POST",
  });
  return resp.json();
}

export async function cancelInvite(
  inviteId: string
): Promise<{ invite_id: string; status: "cancelled" }> {
  const resp = await authFetch(`/invites/${inviteId}`, { method: "DELETE" });
  return resp.json();
}

export async function getInviteInbox(params: {
  status?: string;
  cursor?: string;
  limit?: number;
}): Promise<InviteListResponse> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.cursor) qs.set("cursor", params.cursor);
  if (params.limit) qs.set("limit", String(params.limit));

  const resp = await authFetch(`/invites/inbox?${qs.toString()}`);
  return resp.json() as Promise<InviteListResponse>;
}

export async function getSentInvites(params: {
  status?: string;
  cursor?: string;
  limit?: number;
}): Promise<InviteListResponse> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.cursor) qs.set("cursor", params.cursor);
  if (params.limit) qs.set("limit", String(params.limit));

  const resp = await authFetch(`/invites/sent?${qs.toString()}`);
  return resp.json() as Promise<InviteListResponse>;
}

// ---------------------------------------------------------------------------
// Block endpoints
// ---------------------------------------------------------------------------

export async function blockProfile(
  profileId: string,
  reason?: "harassment" | "spam" | "inappropriate_content" | "other"
): Promise<BlockResponse> {
  const resp = await authFetch(`/blocks/${profileId}`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
  return resp.json() as Promise<BlockResponse>;
}

export async function unblockProfile(profileId: string): Promise<{ unblocked: boolean }> {
  const resp = await authFetch(`/blocks/${profileId}`, { method: "DELETE" });
  return resp.json();
}

export async function getBlocks(params: {
  cursor?: string;
  limit?: number;
}): Promise<BlockListResponse> {
  const qs = new URLSearchParams();
  if (params.cursor) qs.set("cursor", params.cursor);
  if (params.limit) qs.set("limit", String(params.limit));

  const resp = await authFetch(`/blocks?${qs.toString()}`);
  return resp.json() as Promise<BlockListResponse>;
}
