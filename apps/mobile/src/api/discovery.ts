/**
 * discovery-svc API client — typed wrappers for all discovery endpoints.
 *
 * Base URL comes from EXPO_PUBLIC_API_BASE_URL env var.
 * All mutating requests include the access token from auth store.
 */

import { useAuthStore } from "../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FeedMode = "scroll" | "swipe";

export interface VocationCard {
  category: string;
  subtag: string;
}

export interface PortfolioPreview {
  type: "image" | "video" | "link";
  url: string;
  caption: string;
}

export interface ProfileCard {
  id: string;
  display_name: string;
  location_city: string | null;
  badge_state: "badge_granted" | "pending" | "not_applied";
  vocations: VocationCard[];
  bio: string | null;
  obsessed_with: string | null;
  experience_level: number;
  open_to_remote: boolean;
  portfolio_preview: PortfolioPreview[];
  collab_count: number;
  last_active_relative: string;
  saved: boolean;
  avatar_url: string | null;
  // NOTE: match_score and profile_health_score are NEVER included per spec
}

export interface FeedFilters {
  vocation_categories?: string[];
  radius_km?: number;
  anywhere?: boolean;
  experience_level_min?: number;
  experience_level_max?: number;
  open_to_remote?: boolean;
  last_active_days?: number;
  min_successful_collabs?: number;
}

export interface FeedResponse {
  mode: FeedMode;
  profiles: ProfileCard[];
  next_cursor: string | null;
  remaining_today?: number;
  cap?: number;
}

export interface PickedForYouResponse {
  profiles: ProfileCard[];
  generated_at: string;
  next_refresh_at: string;
}

export interface DailyCapError {
  error: "daily_cap_reached";
  cap: number;
  resets_at: string;
}

export interface HideResponse {
  hidden_until: string;
}

export interface SaveResponse {
  saved_at: string;
}

export interface ApiError {
  error: string;
  message: string;
  details?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken;
}

function authHeaders(): Record<string, string> {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = { error: "unknown", message: res.statusText };
    }
    const err = new Error((body as ApiError).message ?? res.statusText) as Error & {
      status: number;
      body: unknown;
    };
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Feed API
// ---------------------------------------------------------------------------

export async function getFeed(params: {
  mode?: FeedMode;
  cursor?: string | null;
  pageSize?: number;
  filters?: FeedFilters;
}): Promise<FeedResponse> {
  const { mode = "scroll", cursor, pageSize = 20, filters } = params;

  const qs = new URLSearchParams();
  qs.set("mode", mode);
  qs.set("page_size", String(pageSize));
  if (cursor) qs.set("cursor", cursor);
  if (filters && Object.keys(filters).length > 0) {
    qs.set("filters", encodeURIComponent(JSON.stringify(filters)));
  }

  const res = await fetch(`${BASE_URL}/feed?${qs.toString()}`, {
    headers: authHeaders(),
  });
  return handleResponse<FeedResponse>(res);
}

export async function setFeedMode(mode: FeedMode): Promise<{ mode: FeedMode; updated_at: string }> {
  const res = await fetch(`${BASE_URL}/feed/preference/mode`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  return handleResponse(res);
}

export async function getPickedForYou(): Promise<PickedForYouResponse> {
  const res = await fetch(`${BASE_URL}/feed/picked-for-you`, {
    headers: authHeaders(),
  });
  return handleResponse<PickedForYouResponse>(res);
}

// ---------------------------------------------------------------------------
// Profile actions
// ---------------------------------------------------------------------------

export async function hideProfile(profileId: string): Promise<HideResponse> {
  const res = await fetch(`${BASE_URL}/profile/${profileId}/hide-3mo`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<HideResponse>(res);
}

export async function unhideProfile(profileId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/profile/${profileId}/hide-3mo`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok && res.status !== 404) {
    return handleResponse(res);
  }
}

export async function saveProfile(profileId: string): Promise<SaveResponse> {
  const res = await fetch(`${BASE_URL}/profile/${profileId}/save`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<SaveResponse>(res);
}

export async function unsaveProfile(profileId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/profile/${profileId}/save`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok && res.status !== 404) {
    return handleResponse(res);
  }
}

export async function getSavedProfiles(): Promise<{ profiles: ProfileCard[] }> {
  const res = await fetch(`${BASE_URL}/me/saved`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}
