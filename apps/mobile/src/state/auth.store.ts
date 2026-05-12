/**
 * Auth Zustand store — tokens + user; persisted via expo-secure-store.
 *
 * - Access token: memory only (non-persisted).
 * - Refresh token: persisted in Keychain/Keystore via expo-secure-store.
 */

import * as SecureStore from "expo-secure-store";
import { create } from "zustand";

const REFRESH_TOKEN_KEY = "colab:refresh_token";

export interface AuthUser {
  userId: string;
  email: string;
  tier: "free" | "premium" | "premium_pro";
  roles: string[];
}

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;

  hydrate: () => Promise<void>;
  setTokens: (accessToken: string, refreshToken: string, user: AuthUser) => Promise<void>;
  clearTokens: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,

  hydrate: async () => {
    try {
      const storedRefreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
      if (!storedRefreshToken) {
        set({ isAuthenticated: false });
        return;
      }
      // P2a: call /auth/token/refresh → rotate token and restore session
      const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";
      const resp = await fetch(`${BASE_URL}/auth/token/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: storedRefreshToken }),
      });
      if (!resp.ok) {
        await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
        set({ isAuthenticated: false });
        return;
      }
      const data = await resp.json();
      // Rotate refresh token in secure store
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, data.refresh_token);
      // Parse user from JWT claims (without full sig verify — gateway verifies on every API call)
      let user: AuthUser | null = null;
      try {
        const parts = data.access_token.split(".");
        const payload = JSON.parse(
          decodeURIComponent(
            atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"))
              .split("")
              .map((c: string) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
              .join("")
          )
        );
        user = {
          userId: payload.sub,
          email: payload.email ?? "",
          tier: (payload.tier ?? "free") as AuthUser["tier"],
          roles: payload.scope ?? [],
        };
      } catch {
        user = null;
      }
      set({ accessToken: data.access_token, user, isAuthenticated: !!user });
    } catch {
      set({ isAuthenticated: false });
    }
  },

  setTokens: async (accessToken, refreshToken, user) => {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
    set({ accessToken, user, isAuthenticated: true });
  },

  clearTokens: async () => {
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
    set({ accessToken: null, user: null, isAuthenticated: false });
  },
}));
