"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@colab/ui";
import { api, ApiError } from "../../lib/api";

interface FeedProfile {
  user_id: string;
  display_name: string;
  bio?: string | null;
  vocations?: string[];
  location_label?: string | null;
  avatar_url?: string | null;
  match_score?: number;
}

interface FeedResponse {
  items: FeedProfile[];
  next_cursor?: string | null;
  daily_views_remaining?: number;
}

export default function DiscoverPage(): React.ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const feed = useQuery<FeedResponse, ApiError>({
    queryKey: ["discover", "feed"],
    queryFn: () => api.get<FeedResponse>("/v1/feed?limit=24"),
    enabled: !!user,
    retry: (count, e) => e.status >= 500 && count < 2,
  });

  if (loading || !user) {
    return (
      <main className="container mx-auto max-w-6xl px-4 py-12 text-center">
        <p className="text-[var(--color-muted-foreground)]">Loading…</p>
      </main>
    );
  }

  return (
    <main className="container mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Discover creators</h1>
          <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">
            People you might want to collaborate with.
          </p>
        </div>
        {typeof feed.data?.daily_views_remaining === "number" && (
          <p className="text-xs text-[var(--color-muted-foreground)]">
            {feed.data.daily_views_remaining} profile views left today
          </p>
        )}
      </div>

      {feed.isLoading && (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
          {Array.from({ length: 6 }).map((_, i) => (
            <li
              key={i}
              className="h-48 animate-pulse rounded-xl border border-[var(--color-border)] bg-[var(--color-muted)]"
            />
          ))}
        </ul>
      )}

      {feed.error && (
        <div
          role="alert"
          className="rounded-md border border-[var(--color-destructive)] bg-[color-mix(in_srgb,var(--color-destructive)_10%,white)] px-4 py-3 text-sm text-[var(--color-destructive)]"
        >
          <p>We couldn&apos;t load your feed: {feed.error.message}</p>
          <button
            type="button"
            onClick={() => void feed.refetch()}
            className="mt-2 text-sm font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {feed.data && feed.data.items.length === 0 && (
        <div className="rounded-xl border border-dashed border-[var(--color-border)] p-12 text-center">
          <h2 className="text-lg font-semibold">No matches yet</h2>
          <p className="mt-2 text-sm text-[var(--color-muted-foreground)]">
            We&apos;re still indexing creators in your area. Check back tomorrow, or
            broaden your search radius in{" "}
            <Link href="/settings" className="text-[var(--color-brand-primary)] underline">
              Settings
            </Link>
            .
          </p>
        </div>
      )}

      {feed.data && feed.data.items.length > 0 && (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" role="list">
          {feed.data.items.map((p) => (
            <li key={p.user_id}>
              <Link
                href={`/profile/${p.user_id}`}
                className="group block h-full rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 transition-colors hover:border-[var(--color-brand-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
              >
                <div className="flex items-center gap-3">
                  {p.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={p.avatar_url}
                      alt=""
                      className="h-12 w-12 rounded-full object-cover"
                    />
                  ) : (
                    <span
                      className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-muted)] text-lg font-semibold text-[var(--color-muted-foreground)]"
                      aria-hidden="true"
                    >
                      {p.display_name[0]?.toUpperCase() ?? "?"}
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-[var(--color-foreground)] group-hover:text-[var(--color-brand-primary)]">
                      {p.display_name}
                    </p>
                    {p.location_label && (
                      <p className="truncate text-xs text-[var(--color-muted-foreground)]">
                        {p.location_label}
                      </p>
                    )}
                  </div>
                </div>
                {p.bio && (
                  <p className="mt-3 line-clamp-2 text-sm text-[var(--color-muted-foreground)]">
                    {p.bio}
                  </p>
                )}
                {p.vocations && p.vocations.length > 0 && (
                  <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Vocations">
                    {p.vocations.slice(0, 3).map((v) => (
                      <li
                        key={v}
                        className="rounded-full bg-[var(--color-muted)] px-2 py-0.5 text-xs text-[var(--color-muted-foreground)]"
                      >
                        {v}
                      </li>
                    ))}
                  </ul>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
