/**
 * gateway-svc typed client wrapper.
 * DO NOT EDIT MANUALLY. Run `make openapi` to regenerate.
 */

import type { components, paths } from "./schema";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type ReadyResponse = components["schemas"]["ReadyResponse"];
export type VersionResponse = components["schemas"]["VersionResponse"];
export type FlagsResponse = components["schemas"]["FlagsResponse"];

interface ClientOptions {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
  requestId?: () => string;
}

type FetchResult<T> = Promise<T>;

function defaultRequestId(): string {
  return crypto.randomUUID();
}

/**
 * Create a typed gateway-svc client.
 *
 * Usage:
 *   const gateway = createGatewayClient({ baseUrl: "https://api.colab.app" });
 *   const health = await gateway.healthz();
 */
export function createGatewayClient(opts: ClientOptions = {}): {
  healthz: () => FetchResult<HealthResponse>;
  readyz: () => FetchResult<ReadyResponse>;
  version: () => FetchResult<VersionResponse>;
  getFlags: () => FetchResult<FlagsResponse>;
} {
  const { baseUrl = "", getAccessToken, requestId = defaultRequestId } = opts;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Request-Id": requestId(),
      ...(init.headers as Record<string, string> | undefined),
    };

    const token = getAccessToken?.();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    let retries = 0;
    while (true) {
      const resp = await fetch(`${baseUrl}${path}`, { ...init, headers });

      if (resp.status === 429 && retries < 3) {
        const retryAfter = parseInt(resp.headers.get("Retry-After") ?? "5", 10);
        await new Promise((r) => setTimeout(r, retryAfter * 1000));
        retries++;
        continue;
      }

      if (!resp.ok) {
        const error = (await resp.json().catch(() => ({ error: { message: resp.statusText } }))) as {
          error: { message: string; code?: string };
        };
        throw new Error(
          `[gateway-svc] ${resp.status}: ${error.error?.message ?? resp.statusText}`
        );
      }

      return resp.json() as Promise<T>;
    }
  }

  return {
    healthz: () => request<HealthResponse>("/healthz"),
    readyz: () => request<ReadyResponse>("/ready"),
    version: () => request<VersionResponse>("/version"),
    getFlags: () => request<FlagsResponse>("/v1/flags"),
  };
}
