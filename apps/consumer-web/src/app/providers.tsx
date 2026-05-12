"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, ThemeProvider } from "@colab/ui";
import React, { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }): React.ReactElement {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 60_000 },
        },
      })
  );

  return (
    <ThemeProvider defaultTheme="system">
      <AuthProvider apiBaseUrl={process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
