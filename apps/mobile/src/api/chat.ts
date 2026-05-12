/**
 * chat-svc REST API client — typed wrappers for all chat endpoints.
 * WebSocket logic lives in hooks/useChatSocket.ts.
 */

import Constants from "expo-constants";
import { useAuthStore } from "../state/auth.store";

const apiBaseUrl: string =
  (Constants.expoConfig?.extra as Record<string, string> | undefined)?.apiBaseUrl ??
  "http://localhost:8000";

const wsBaseUrl: string = apiBaseUrl.replace(/^http/, "ws");

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProfileStub {
  profile_id: string;
  display_name: string | null;
  avatar_url: string | null;
}

export interface ChatMessageOut {
  id: string;
  room_id: string;
  sender_profile_id: string;
  sender?: ProfileStub;
  type: "text" | "voice" | "image" | "video" | "audio" | "doc" | "link" | "system";
  body?: string;
  media_key?: string;
  media_url?: string;
  mime?: string;
  size_bytes?: number;
  duration_ms?: number;
  reply_to?: string;
  reply_preview?: {
    id: string;
    sender_profile_id: string;
    type: string;
    body?: string;
  };
  moderation_status: "allowed" | "soft_warn" | "hidden" | "auto_hidden";
  edited_at?: string;
  created_at: string;
}

export interface ChatRoomSummary {
  id: string;
  collaboration_id: string;
  state: "open" | "read_only" | "archived";
  participants: ProfileStub[];
  last_message?: ChatMessageOut;
  unread_count: number;
  created_at: string;
}

export interface ChatRoomDetail {
  id: string;
  collaboration_id: string;
  state: "open" | "read_only" | "archived";
  participants: ProfileStub[];
  read_receipts: Array<{
    profile_id: string;
    last_read_msg_id?: string;
    last_read_at?: string;
  }>;
  created_at: string;
  archived_at?: string;
}

export interface UploadUrlResponse {
  upload_url: string;
  s3_key: string;
}

export interface ConfirmResponse {
  status: string;
  pending_msg_id: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { ...getHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Room endpoints
// ---------------------------------------------------------------------------

export async function listRooms(params?: {
  cursor?: string;
  limit?: number;
}): Promise<{ rooms: ChatRoomSummary[]; next_cursor?: string }> {
  const qs = new URLSearchParams();
  if (params?.cursor) qs.set("cursor", params.cursor);
  if (params?.limit) qs.set("limit", String(params.limit));
  return apiFetch(`/chat/rooms${qs.toString() ? `?${qs}` : ""}`);
}

export async function getRoom(roomId: string): Promise<ChatRoomDetail> {
  return apiFetch(`/chat/rooms/${roomId}`);
}

export async function getMessages(
  roomId: string,
  params?: { cursor?: string; limit?: number; direction?: "before" | "after" }
): Promise<{ messages: ChatMessageOut[]; next_cursor?: string }> {
  const qs = new URLSearchParams();
  if (params?.cursor) qs.set("cursor", params.cursor);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.direction) qs.set("direction", params.direction);
  return apiFetch(`/chat/rooms/${roomId}/messages${qs.toString() ? `?${qs}` : ""}`);
}

export async function sendMessage(
  roomId: string,
  body: { body: string; reply_to?: string; client_nonce: string }
): Promise<ChatMessageOut> {
  return apiFetch(`/chat/rooms/${roomId}/messages`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function editMessage(
  roomId: string,
  msgId: string,
  body: string
): Promise<ChatMessageOut> {
  return apiFetch(`/chat/rooms/${roomId}/messages/${msgId}/edit`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export async function markRead(roomId: string, upToMsgId: string): Promise<void> {
  return apiFetch(`/chat/rooms/${roomId}/read`, {
    method: "POST",
    body: JSON.stringify({ up_to_msg_id: upToMsgId }),
  });
}

// ---------------------------------------------------------------------------
// Media endpoints
// ---------------------------------------------------------------------------

export async function getUploadUrl(params: {
  room_id: string;
  kind: "image" | "audio" | "video" | "doc" | "voice";
  mime: string;
  size_bytes: number;
}): Promise<UploadUrlResponse> {
  return apiFetch("/media/upload-url", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function confirmUpload(params: {
  room_id: string;
  kind: string;
  s3_key: string;
  mime: string;
  size_bytes: number;
  duration_ms?: number;
}): Promise<ConfirmResponse> {
  return apiFetch("/media/confirm", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getSignedUrl(s3Key: string, roomId: string): Promise<string> {
  const res = await apiFetch<{ url: string; expires_at: string }>(
    `/media/${encodeURIComponent(s3Key)}/signed-url?room_id=${roomId}`
  );
  return res.url;
}

// ---------------------------------------------------------------------------
// WebSocket URL factory
// ---------------------------------------------------------------------------

export function getChatWsUrl(roomId: string): string {
  const token = useAuthStore.getState().accessToken ?? "";
  return `${wsBaseUrl}/chat/${roomId}?token=${encodeURIComponent(token)}`;
}
