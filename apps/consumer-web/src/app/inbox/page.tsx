"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, useAuth } from "@colab/ui";
import { api, ApiError } from "../../lib/api";

type Tab = "received" | "sent" | "matches";

interface VibeCheck {
  id: string;
  sender_user_id: string;
  recipient_user_id: string;
  sender_display_name?: string;
  recipient_display_name?: string;
  message?: string | null;
  state: "pending" | "accepted" | "rejected" | "expired";
  created_at: string;
}

interface Match {
  id: string;
  other_user_id: string;
  other_display_name?: string;
  matched_at: string;
  room_id?: string;
}

export default function InboxPage(): React.ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("received");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const received = useQuery<{ items: VibeCheck[] }, ApiError>({
    queryKey: ["inbox", "received"],
    queryFn: () => api.get("/v1/invite/received"),
    enabled: !!user && tab === "received",
  });
  const sent = useQuery<{ items: VibeCheck[] }, ApiError>({
    queryKey: ["inbox", "sent"],
    queryFn: () => api.get("/v1/invite/sent"),
    enabled: !!user && tab === "sent",
  });
  const matches = useQuery<{ items: Match[] }, ApiError>({
    queryKey: ["inbox", "matches"],
    queryFn: () => api.get("/v1/invite/matches"),
    enabled: !!user && tab === "matches",
  });

  const decide = useMutation<unknown, ApiError, { id: string; action: "accept" | "reject" }>({
    mutationFn: ({ id, action }) => api.post(`/v1/invite/${id}/${action}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["inbox"] });
    },
  });

  if (loading || !user) {
    return (
      <main className="container mx-auto max-w-4xl px-4 py-12 text-center">
        <p className="text-[var(--color-muted-foreground)]">Loading…</p>
      </main>
    );
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: "received", label: "Received" },
    { id: "sent", label: "Sent" },
    { id: "matches", label: "Matches" },
  ];

  return (
    <main className="container mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-bold">Inbox</h1>

      <nav className="mt-6 border-b border-[var(--color-border)]" aria-label="Inbox tabs">
        <ul className="flex gap-1" role="tablist">
          {TABS.map((t) => (
            <li key={t.id}>
              <button
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`relative -mb-px px-3 py-2 text-sm font-medium transition-colors ${
                  tab === t.id
                    ? "border-b-2 border-[var(--color-brand-primary)] text-[var(--color-foreground)]"
                    : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
                }`}
              >
                {t.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-6">
        {tab === "received" && (
          <InviteList
            items={received.data?.items ?? []}
            loading={received.isLoading}
            error={received.error?.message}
            onAccept={(id) => decide.mutate({ id, action: "accept" })}
            onReject={(id) => decide.mutate({ id, action: "reject" })}
            who="sender"
          />
        )}
        {tab === "sent" && (
          <InviteList
            items={sent.data?.items ?? []}
            loading={sent.isLoading}
            error={sent.error?.message}
            who="recipient"
          />
        )}
        {tab === "matches" && (
          <MatchList
            items={matches.data?.items ?? []}
            loading={matches.isLoading}
            error={matches.error?.message}
          />
        )}
      </div>
    </main>
  );
}

function InviteList(props: {
  items: VibeCheck[];
  loading: boolean;
  error: string | undefined;
  onAccept?: ((id: string) => void) | undefined;
  onReject?: ((id: string) => void) | undefined;
  who: "sender" | "recipient";
}): React.ReactElement {
  if (props.loading) return <p className="text-sm text-[var(--color-muted-foreground)]">Loading…</p>;
  if (props.error)
    return (
      <p role="alert" className="text-sm text-[var(--color-destructive)]">
        {props.error}
      </p>
    );
  if (props.items.length === 0)
    return (
      <p className="rounded-md border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-muted-foreground)]">
        Nothing here yet.
      </p>
    );

  return (
    <ul className="space-y-3" role="list">
      {props.items.map((v) => {
        const who =
          props.who === "sender"
            ? v.sender_display_name ?? v.sender_user_id.slice(0, 8)
            : v.recipient_display_name ?? v.recipient_user_id.slice(0, 8);
        return (
          <li key={v.id}>
            <Card>
              <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-medium">{who}</p>
                  {v.message && (
                    <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">{v.message}</p>
                  )}
                  <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
                    {new Date(v.created_at).toLocaleDateString()} ·{" "}
                    <span className="capitalize">{v.state}</span>
                  </p>
                </div>
                {props.onAccept && props.onReject && v.state === "pending" && (
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => props.onReject?.(v.id)}
                    >
                      Pass
                    </Button>
                    <Button type="button" onClick={() => props.onAccept?.(v.id)}>
                      Accept
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

function MatchList(props: {
  items: Match[];
  loading: boolean;
  error: string | undefined;
}): React.ReactElement {
  if (props.loading) return <p className="text-sm text-[var(--color-muted-foreground)]">Loading…</p>;
  if (props.error)
    return (
      <p role="alert" className="text-sm text-[var(--color-destructive)]">
        {props.error}
      </p>
    );
  if (props.items.length === 0)
    return (
      <p className="rounded-md border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-muted-foreground)]">
        No matches yet — send a Vibe Check to get started.
      </p>
    );
  return (
    <ul className="space-y-3" role="list">
      {props.items.map((m) => (
        <li key={m.id}>
          <Card>
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div>
                <p className="font-medium">
                  {m.other_display_name ?? m.other_user_id.slice(0, 8)}
                </p>
                <p className="mt-0.5 text-xs text-[var(--color-muted-foreground)]">
                  Matched {new Date(m.matched_at).toLocaleDateString()}
                </p>
              </div>
              {m.room_id ? (
                <Button asChild>
                  <Link href={`/chats/${m.room_id}`}>Open chat</Link>
                </Button>
              ) : (
                <Button asChild variant="outline">
                  <Link href={`/profile/${m.other_user_id}`}>View profile</Link>
                </Button>
              )}
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
