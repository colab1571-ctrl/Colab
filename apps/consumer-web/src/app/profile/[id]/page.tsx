"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, useAuth } from "@colab/ui";
import { api, ApiError } from "../../../lib/api";

interface ProfileDetail {
  user_id: string;
  display_name: string;
  bio?: string | null;
  vocations?: string[];
  location_label?: string | null;
  avatar_url?: string | null;
  open_to_remote?: boolean;
  portfolio_items?: PortfolioItem[];
  externals?: Record<string, string>;
}

interface PortfolioItem {
  id: string;
  title?: string;
  media_url: string;
  kind: "image" | "audio" | "video" | "doc";
}

export default function ProfileDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}): React.ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [resolvedId, setResolvedId] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendSuccess, setSendSuccess] = useState(false);

  useEffect(() => {
    void params.then((p) => setResolvedId(p.id === "me" ? user?.userId ?? null : p.id));
  }, [params, user]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const profile = useQuery<ProfileDetail, ApiError>({
    queryKey: ["profile", resolvedId],
    queryFn: () => api.get<ProfileDetail>(`/v1/profile/${resolvedId}`),
    enabled: !!resolvedId,
  });

  const isMe = resolvedId && user && resolvedId === user.userId;

  const sendVibe = useMutation<unknown, ApiError, { message?: string }>({
    mutationFn: (body) =>
      api.post(`/v1/invite/vibe-check`, {
        recipient_user_id: resolvedId,
        message: body.message ?? "",
      }),
    onSuccess: () => {
      setSendSuccess(true);
      setSendError(null);
      void qc.invalidateQueries({ queryKey: ["inbox"] });
    },
    onError: (e) => setSendError(e.message),
  });

  if (loading || !user || profile.isLoading) {
    return (
      <main className="container mx-auto max-w-3xl px-4 py-12 text-center">
        <p className="text-[var(--color-muted-foreground)]">Loading…</p>
      </main>
    );
  }

  if (profile.error || !profile.data) {
    return (
      <main className="container mx-auto max-w-3xl px-4 py-12">
        <p
          role="alert"
          className="rounded-md border border-[var(--color-destructive)] bg-[color-mix(in_srgb,var(--color-destructive)_10%,white)] px-4 py-3 text-sm text-[var(--color-destructive)]"
        >
          Couldn&apos;t load this profile: {profile.error?.message ?? "Unknown error"}
        </p>
      </main>
    );
  }

  const p = profile.data;

  return (
    <main className="container mx-auto max-w-3xl px-4 py-8">
      <header className="flex flex-col items-start gap-4 sm:flex-row">
        {p.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={p.avatar_url} alt="" className="h-24 w-24 rounded-full object-cover" />
        ) : (
          <span
            className="flex h-24 w-24 items-center justify-center rounded-full bg-[var(--color-muted)] text-3xl font-semibold text-[var(--color-muted-foreground)]"
            aria-hidden="true"
          >
            {p.display_name[0]?.toUpperCase() ?? "?"}
          </span>
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{p.display_name}</h1>
          {p.location_label && (
            <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">
              {p.location_label}
              {p.open_to_remote && " · Open to remote"}
            </p>
          )}
          {p.vocations && p.vocations.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Vocations">
              {p.vocations.map((v) => (
                <li
                  key={v}
                  className="rounded-full bg-[var(--color-muted)] px-2.5 py-0.5 text-xs text-[var(--color-muted-foreground)]"
                >
                  {v}
                </li>
              ))}
            </ul>
          )}
        </div>
        {!isMe && (
          <Button
            onClick={() => void sendVibe.mutate({})}
            disabled={sendVibe.isPending || sendSuccess}
          >
            {sendSuccess
              ? "Vibe Check sent ✓"
              : sendVibe.isPending
                ? "Sending…"
                : "Send Vibe Check"}
          </Button>
        )}
      </header>

      {sendError && (
        <p role="alert" className="mt-3 text-sm text-[var(--color-destructive)]">
          {sendError}
        </p>
      )}

      {p.bio && (
        <section className="mt-6">
          <h2 className="text-sm font-semibold uppercase text-[var(--color-muted-foreground)]">About</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm">{p.bio}</p>
        </section>
      )}

      {p.portfolio_items && p.portfolio_items.length > 0 && (
        <section className="mt-8">
          <h2 className="text-sm font-semibold uppercase text-[var(--color-muted-foreground)]">
            Portfolio
          </h2>
          <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3" role="list">
            {p.portfolio_items.map((item) => (
              <li key={item.id}>
                <Card>
                  <CardContent className="p-2">
                    {item.kind === "image" ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={item.media_url}
                        alt={item.title ?? ""}
                        className="aspect-square w-full rounded object-cover"
                      />
                    ) : (
                      <div className="flex aspect-square w-full items-center justify-center rounded bg-[var(--color-muted)] text-xs text-[var(--color-muted-foreground)]">
                        {item.kind.toUpperCase()}
                      </div>
                    )}
                    {item.title && (
                      <p className="mt-2 truncate text-xs text-[var(--color-muted-foreground)]">
                        {item.title}
                      </p>
                    )}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {isMe && (!p.portfolio_items || p.portfolio_items.length === 0) && (
        <div className="mt-8 rounded-xl border border-dashed border-[var(--color-border)] p-8 text-center">
          <p className="text-sm text-[var(--color-muted-foreground)]">
            Your portfolio is empty. Add a few of your favourite pieces so collaborators get a sense
            of your work.
          </p>
          <Button asChild className="mt-4">
            <a href="/onboarding">Set up profile</a>
          </Button>
        </div>
      )}
    </main>
  );
}
