/**
 * Next.js instrumentation hook — Sentry server-side init.
 */

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { default: * as Sentry } = await import("@sentry/nextjs");
    // Sentry.init is called via sentry.server.config.ts; this ensures the SDK is loaded.
  }
}
