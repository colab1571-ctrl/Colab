/**
 * Auth API client — typed wrappers around the auth-svc REST endpoints.
 *
 * Base URL read from EXPO_PUBLIC_API_BASE_URL env var.
 * All requests include the access token from the auth store.
 * Token refresh is handled transparently via the interceptor pattern.
 */

import { useAuthStore } from "../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TokenPair {
  user_id: string;
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
  expires_in: number;
}

export interface SessionOut {
  id: string;
  user_agent: string | null;
  ip: string | null;
  last_seen_at: string;
  created_at: string;
  is_current: boolean;
}

export interface IdentityVerificationState {
  user_id: string;
  persona_inquiry_id: string | null;
  status: "pending" | "approved" | "declined" | "needs_review";
  face_age_signal: string | null;
  decision_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
  };
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

async function request<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {}
): Promise<T> {
  const { auth = false, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (auth) {
    const { accessToken } = useAuthStore.getState();
    if (accessToken) {
      headers["Authorization"] = `Bearer ${accessToken}`;
    }
  }

  const resp = await fetch(`${BASE_URL}${path}`, {
    ...fetchOptions,
    headers,
  });

  const data = await resp.json();
  if (!resp.ok) {
    throw data as ApiError;
  }
  return data as T;
}

// ---------------------------------------------------------------------------
// Signup
// ---------------------------------------------------------------------------

export async function signupEmail(params: {
  email: string;
  password: string;
}): Promise<TokenPair> {
  return request<TokenPair>("/auth/signup/email", {
    method: "POST",
    body: JSON.stringify({
      ...params,
      age_attestation: true,
      accept_tos: true,
      accept_privacy: true,
      accept_community: true,
    }),
  });
}

export async function signupOAuth(params: {
  provider: "apple" | "google";
  id_token: string;
  nonce?: string;
}): Promise<TokenPair> {
  return request<TokenPair>("/auth/signup/oauth", {
    method: "POST",
    body: JSON.stringify({
      ...params,
      age_attestation: true,
      accept_tos: true,
      accept_privacy: true,
      accept_community: true,
    }),
  });
}

export async function signupPhoneStart(phone: string): Promise<{ otp_sent: boolean; phone: string }> {
  return request("/auth/signup/phone", {
    method: "POST",
    body: JSON.stringify({
      phone,
      age_attestation: true,
      accept_tos: true,
      accept_privacy: true,
      accept_community: true,
    }),
  });
}

export async function signupPhoneVerify(phone: string, code: string): Promise<TokenPair> {
  return request<TokenPair>("/auth/signup/phone/verify", {
    method: "POST",
    body: JSON.stringify({ phone, code }),
  });
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

export async function loginEmail(email: string, password: string): Promise<TokenPair> {
  return request<TokenPair>("/auth/login/email", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function loginOAuth(params: {
  provider: "apple" | "google";
  id_token: string;
  nonce?: string;
}): Promise<TokenPair> {
  return request<TokenPair>("/auth/login/oauth", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function loginPhoneStart(phone: string): Promise<{ otp_sent: boolean; phone: string }> {
  return request("/auth/login/phone/start", {
    method: "POST",
    body: JSON.stringify({ phone }),
  });
}

export async function loginPhoneVerify(phone: string, code: string): Promise<TokenPair> {
  return request<TokenPair>("/auth/login/phone/verify", {
    method: "POST",
    body: JSON.stringify({ phone, code }),
  });
}

// ---------------------------------------------------------------------------
// Email verification
// ---------------------------------------------------------------------------

export async function emailVerifyStart(email: string): Promise<{ message: string }> {
  return request("/auth/email/verify/start", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function emailVerifyFinish(params: {
  token?: string;
  code?: string;
}): Promise<{ email_verified: boolean }> {
  return request("/auth/email/verify/finish", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// ---------------------------------------------------------------------------
// Password reset
// ---------------------------------------------------------------------------

export async function passwordResetStart(email: string): Promise<{ message: string }> {
  return request("/auth/password/reset/start", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function passwordResetFinish(token: string, newPassword: string): Promise<{ password_reset: boolean }> {
  return request("/auth/password/reset/finish", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

// ---------------------------------------------------------------------------
// Token management
// ---------------------------------------------------------------------------

export async function refreshToken(refreshToken: string): Promise<TokenPair> {
  return request<TokenPair>("/auth/token/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function logout(refreshToken: string): Promise<{ logged_out: boolean }> {
  return request("/auth/logout", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
    auth: true,
  });
}

export async function logoutAll(): Promise<{ logged_out: boolean }> {
  return request("/auth/logout/all", { method: "POST", auth: true });
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export async function getSessions(): Promise<{ sessions: SessionOut[] }> {
  return request("/auth/sessions", { method: "GET", auth: true });
}

export async function revokeSession(sessionId: string): Promise<{ sessions: SessionOut[] }> {
  return request(`/auth/sessions/${sessionId}`, { method: "DELETE", auth: true });
}

// ---------------------------------------------------------------------------
// Account management
// ---------------------------------------------------------------------------

export async function emailChangeStart(newEmail: string): Promise<{ message: string }> {
  return request("/auth/account/email/change/start", {
    method: "POST",
    body: JSON.stringify({ new_email: newEmail }),
    auth: true,
  });
}

export async function emailChangeFinish(params: {
  token?: string;
  code?: string;
}): Promise<{ email_changed: boolean }> {
  return request("/auth/account/email/change/finish", {
    method: "POST",
    body: JSON.stringify(params),
    auth: true,
  });
}

export async function phoneChangeStart(newPhone: string): Promise<{ otp_sent: boolean }> {
  return request("/auth/account/phone/change/start", {
    method: "POST",
    body: JSON.stringify({ new_phone: newPhone }),
    auth: true,
  });
}

export async function phoneChangeFinish(newPhone: string, code: string): Promise<{ phone_changed: boolean }> {
  return request("/auth/account/phone/change/finish", {
    method: "POST",
    body: JSON.stringify({ new_phone: newPhone, code }),
    auth: true,
  });
}
