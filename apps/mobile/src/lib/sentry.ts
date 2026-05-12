import * as Sentry from "@sentry/react-native";
import Constants from "expo-constants";

export function initSentry(): void {
  const dsn = (Constants.expoConfig?.extra as Record<string, string> | undefined)?.sentryDsn;
  if (!dsn) return;

  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV ?? "development",
    tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,
    enableAutoSessionTracking: true,
    sessionTrackingIntervalMillis: 30_000,
  });
}

export { Sentry };
