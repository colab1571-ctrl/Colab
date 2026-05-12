/**
 * App.tsx — Root entry point with all providers.
 */

import React, { useEffect, useState } from "react";
import { ActivityIndicator, View } from "react-native";
import { QueryClientProvider } from "@tanstack/react-query";
import { RootNavigator } from "../navigation/RootNavigator";
import { useAuthStore } from "../state/auth.store";
import { queryClient } from "../api/client";
import { initSentry } from "../lib/sentry";
import { initPostHog } from "../lib/posthog";
import ErrorBoundary from "./ErrorBoundary";

// Initialize SDKs before render
initSentry();
initPostHog();

export default function App(): React.ReactElement {
  const [ready, setReady] = useState(false);
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    // Hydrate auth from secure storage on cold start
    hydrate().finally(() => setReady(true));
  }, [hydrate]);

  if (!ready) {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator size="large" color="#5B5BD6" />
      </View>
    );
  }

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RootNavigator />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
