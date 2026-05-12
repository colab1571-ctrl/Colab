/**
 * hello-svc typed client wrapper.
 * DO NOT EDIT MANUALLY. Run `make openapi` to regenerate.
 */

import type { components } from "./schema";

export type HelloResponse = components["schemas"]["HelloResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];

interface ClientOptions {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
}

export function createHelloClient(opts: ClientOptions = {}): {
  hello: () => Promise<HelloResponse>;
  healthz: () => Promise<HealthResponse>;
} {
  const { baseUrl = "", getAccessToken } = opts;

  async function request<T>(path: string): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = getAccessToken?.();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const resp = await fetch(`${baseUrl}${path}`, { headers });
    if (!resp.ok) throw new Error(`[hello-svc] ${resp.status}: ${resp.statusText}`);
    return resp.json() as Promise<T>;
  }

  return {
    hello: () => request<HelloResponse>("/hello"),
    healthz: () => request<HealthResponse>("/healthz"),
  };
}
