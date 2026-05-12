"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

export interface AuthUser {
  userId: string;
  email: string;
  roles: string[];
  tier: "free" | "premium" | "premium_pro";
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const ME_ENDPOINT = "/v1/auth/me";

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
    try {
      const resp = await fetch(`${apiBaseUrl}${ME_ENDPOINT}`, { credentials: "include" });
      if (resp.ok) {
        const data = (await resp.json()) as AuthUser;
        setUser(data);
      } else {
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

  const signOut = useCallback(async () => {
    try {
      await fetch(`${apiBaseUrl}/v1/auth/sign-out`, {
        method: "POST",
        credentials: "include",
      });
    } finally {
      setUser(null);
    }
  }, [apiBaseUrl]);

  return (
    <AuthContext.Provider value={{ user, loading, signOut, refresh: fetchMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
