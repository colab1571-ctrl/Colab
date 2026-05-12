"use client";

import { useRouter } from "next/navigation";
import React, { useEffect } from "react";
import { useAuth } from "./AuthProvider";

interface WithAuthOptions {
  requiredRole?: string;
  redirectTo?: string;
}

/**
 * HOC that protects a page component. Redirects to /login if not authenticated.
 * Usage:
 *   export default withAuth(ProfilePage, { requiredRole: "admin" });
 */
export function withAuth<P extends Record<string, unknown>>(
  Component: React.ComponentType<P>,
  options: WithAuthOptions = {}
): React.ComponentType<P> {
  const { requiredRole, redirectTo = "/login" } = options;

  function ProtectedPage(props: P): React.ReactElement | null {
    const { user, loading } = useAuth();
    const router = useRouter();

    useEffect(() => {
      if (!loading && !user) {
        void router.replace(redirectTo);
      }
      if (!loading && user && requiredRole && !user.roles.includes(requiredRole)) {
        void router.replace("/403");
      }
    }, [loading, user, router]);

    if (loading) {
      return (
        <div className="flex h-screen items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--color-primary)] border-t-transparent" />
        </div>
      );
    }

    if (!user) return null;
    if (requiredRole && !user.roles.includes(requiredRole)) return null;

    return <Component {...props} />;
  }

  ProtectedPage.displayName = `withAuth(${Component.displayName ?? Component.name})`;
  return ProtectedPage;
}
