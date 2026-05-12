/**
 * API client factory wiring generated TS clients with auth + retry.
 */

import { QueryClient } from "@tanstack/react-query";
import Constants from "expo-constants";
import { createGatewayClient } from "@colab/api-types/gateway";
import { createHelloClient } from "@colab/api-types/hello";
import { useAuthStore } from "../state/auth.store";

const apiBaseUrl: string =
  (Constants.expoConfig?.extra as Record<string, string> | undefined)?.apiBaseUrl ??
  "http://localhost:8000";

function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken;
}

export const gatewayClient = createGatewayClient({
  baseUrl: apiBaseUrl,
  getAccessToken,
});

export const helloClient = createHelloClient({
  baseUrl: `${apiBaseUrl}/v1/hello`,
  getAccessToken,
});

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 30_000,
      gcTime: 5 * 60 * 1000,
    },
    mutations: {
      retry: 1,
    },
  },
});
