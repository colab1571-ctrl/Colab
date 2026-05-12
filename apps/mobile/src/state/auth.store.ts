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
      const refreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
      if (!refreshToken) {
        set({ isAuthenticated: false });
        return;
      }
      // TODO P2: call /v1/auth/refresh with refreshToken → get new access token
      // For P1, just mark as not authenticated if no refresh token
      set({ isAuthenticated: false });
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
