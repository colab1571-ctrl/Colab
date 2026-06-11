"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@colab/ui";

/**
 * /profile/me redirects to /profile/<your-user-id> so the same detail page
 * powers both views without duplication.
 */
export default function MyProfileRedirect(): React.ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    router.replace(`/profile/${user.userId}`);
  }, [user, loading, router]);

  return (
    <main className="container mx-auto max-w-3xl px-4 py-12 text-center">
      <p className="text-[var(--color-muted-foreground)]">Loading your profile…</p>
    </main>
  );
}
