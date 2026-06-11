"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@colab/ui";
import { api, ApiError } from "../../lib/api";

interface ChatRoom {
  id: string;
  other_user_id?: string;
  other_display_name?: string;
  last_message_preview?: string | null;
  last_message_at?: string;
  unread_count?: number;
}

export default function ChatListPage(): React.ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const rooms = useQuery<{ items: ChatRoom[] }, ApiError>({
    queryKey: ["chats", "rooms"],
    queryFn: () => api.get("/v1/chat/rooms"),
    enabled: !!user,
  });

  if (loading || !user) {
    return (
      <main className="container mx-auto max-w-3xl px-4 py-12 text-center">
        <p className="text-[var(--color-muted-foreground)]">Loading…</p>
      </main>
    );
  }

  return (
    <main className="container mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold">Chats</h1>

      {rooms.isLoading && (
        <ul className="mt-6 space-y-3" aria-busy="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <li
              key={i}
              className="h-16 animate-pulse rounded-md border border-[var(--color-border)] bg-[var(--color-muted)]"
            />
          ))}
        </ul>
      )}

      {rooms.error && (
        <p role="alert" className="mt-6 text-sm text-[var(--color-destructive)]">
          Couldn&apos;t load chats: {rooms.error.message}
        </p>
      )}

      {rooms.data && rooms.data.items.length === 0 && (
        <p className="mt-8 rounded-md border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-muted-foreground)]">
          You don&apos;t have any chats yet. Match with someone in your{" "}
          <Link href="/inbox" className="text-[var(--color-brand-primary)] underline">
            inbox
          </Link>{" "}
          to start a conversation.
        </p>
      )}

      {rooms.data && rooms.data.items.length > 0 && (
        <ul className="mt-6 divide-y divide-[var(--color-border)] rounded-md border border-[var(--color-border)]" role="list">
          {rooms.data.items.map((r) => (
            <li key={r.id}>
              <Link
                href={`/chats/${r.id}`}
                className="flex items-center gap-3 px-4 py-3 hover:bg-[var(--color-muted)] focus-visible:bg-[var(--color-muted)] focus-visible:outline-none"
              >
                <span
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-muted)] text-sm font-semibold text-[var(--color-muted-foreground)]"
                  aria-hidden="true"
                >
                  {(r.other_display_name ?? "?")[0]?.toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {r.other_display_name ?? "Unknown"}
                  </p>
                  {r.last_message_preview && (
                    <p className="truncate text-sm text-[var(--color-muted-foreground)]">
                      {r.last_message_preview}
                    </p>
                  )}
                </div>
                {r.unread_count ? (
                  <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-[var(--color-brand-primary)] px-1.5 text-xs font-semibold text-[var(--color-primary-foreground)]">
                    {r.unread_count}
                  </span>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
