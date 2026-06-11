"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

export interface AuthUser {
  userId: string;
  email: string;
  roles: string[];
  tier: "free" | "premium" | "premium_pro";
}

export interface SignupBody {
  email: string;
  password: string;
  display_name?: string;
  accept_tos: boolean;
  accept_privacy: boolean;
  accept_community: boolean;
  age_attestation: boolean;
  tos_version?: string;
  privacy_version?: string;
  community_version?: string;
}

export interface LoginBody {
  email: string;
  password: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  /** Sign up a new user via POST /v1/auth/signup/email. On success the access token is stored and the user is set. */
  signUp: (body: SignupBody) => Promise<{ ok: true } | { ok: false; error: string }>;
  /** Sign in via POST /v1/auth/login/email. */
  signIn: (body: LoginBody) => Promise<{ ok: true } | { ok: false; error: string }>;
  /** Clear local tokens and (if applicable) call the server logout. */
  signOut: () => Promise<void>;
  /** Re-fetch the current user from the gateway. */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const ME_ENDPOINT = "/v1/auth/me";
const SIGNUP_EMAIL_ENDPOINT = "/v1/auth/signup/email";
const LOGIN_EMAIL_ENDPOINT = "/v1/auth/login/email";
const LOGOUT_ENDPOINT = "/v1/auth/logout";

const TOKEN_STORAGE_KEY = "colab:access_token";
const REFRESH_STORAGE_KEY = "colab:refresh_token";

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredTokens(access: string | null, refresh: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (access) window.localStorage.setItem(TOKEN_STORAGE_KEY, access);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    if (refresh) window.localStorage.setItem(REFRESH_STORAGE_KEY, refresh);
    else window.localStorage.removeItem(REFRESH_STORAGE_KEY);
  } catch {
    // localStorage disabled — fall through silently
  }
}

interface AuthProviderProps {
  children: React.ReactNode;
  /** Base URL for the gateway API. Defaults to empty string (same origin). */
  apiBaseUrl?: string;
}

export function AuthProvider({
  children,
  apiBaseUrl = "",
}: AuthProviderProps): React.ReactElement {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    const token = readStoredToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const resp = await fetch(`${apiBaseUrl}${ME_ENDPOINT}`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (resp.ok) {
        const data = (await resp.json()) as AuthUser;
        setUser(data);
      } else {
        // Token rejected — clear it so we don't keep retrying.
        writeStoredTokens(null, null);
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void fetchMe();
  }, [fetchMe]);

  const handleTokenResponse = useCallback(
    async (resp: Response): Promise<{ ok: true } | { ok: false; error: string }> => {
      if (!resp.ok) {
        let message = `Request failed (${resp.status})`;
        try {
          const body = (await resp.json()) as { detail?: unknown; error?: string };
          if (typeof body.error === "string") message = body.error;
          else if (typeof body.detail === "string") message = body.detail;
          else if (Array.isArray(body.detail) && body.detail.length > 0) {
            const first = body.detail[0] as { msg?: string };
            if (first.msg) message = first.msg;
          }
        } catch {
          /* keep generic message */
        }
        return { ok: false, error: message };
      }
      const payload = (await resp.json()) as {
        access_token?: string;
        refresh_token?: string;
        user_id?: string;
      };
      if (!payload.access_token) {
        return { ok: false, error: "Server did not return an access token." };
      }
      writeStoredTokens(payload.access_token, payload.refresh_token ?? null);
      await fetchMe();
      return { ok: true };
    },
    [fetchMe],
  );

  const signUp = useCallback(
    async (body: SignupBody) => {
      try {
        const resp = await fetch(`${apiBaseUrl}${SIGNUP_EMAIL_ENDPOINT}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            email: body.email,
            password: body.password,
            display_name: body.display_name,
            accept_tos: body.accept_tos,
            accept_privacy: body.accept_privacy,
            accept_community: body.accept_community,
            age_attestation: body.age_attestation,
            tos_version: body.tos_version ?? "1.0",
            privacy_version: body.privacy_version ?? "1.0",
            community_version: body.community_version ?? "1.0",
          }),
        });
        return await handleTokenResponse(resp);
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : "Network error" };
      }
    },
    [apiBaseUrl, handleTokenResponse],
  );

  const signIn = useCallback(
    async (body: LoginBody) => {
      try {
        const resp = await fetch(`${apiBaseUrl}${LOGIN_EMAIL_ENDPOINT}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(body),
        });
        return await handleTokenResponse(resp);
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : "Network error" };
      }
    },
    [apiBaseUrl, handleTokenResponse],
  );

  const signOut = useCallback(async () => {
    const token = readStoredToken();
    try {
      if (token) {
        await fetch(`${apiBaseUrl}${LOGOUT_ENDPOINT}`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          credentials: "include",
        });
      }
    } catch {
      /* network failure — clear locally anyway */
    } finally {
      writeStoredTokens(null, null);
      setUser(null);
    }
  }, [apiBaseUrl]);

  return (
    <AuthContext.Provider value={{ user, loading, signUp, signIn, signOut, refresh: fetchMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
