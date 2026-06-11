"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Input, useAuth } from "@colab/ui";
import { api, ApiError } from "../../../lib/api";

interface Message {
  id: string;
  room_id: string;
  sender_user_id: string;
  body: string;
  content_type?: string;
  created_at: string;
}

export default function ChatRoomPage({
  params,
}: {
  params: Promise<{ id: string }>;
}): React.ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [roomId, setRoomId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void params.then((p) => setRoomId(p.id));
  }, [params]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const messages = useQuery<{ items: Message[] }, ApiError>({
    queryKey: ["chats", "messages", roomId],
    queryFn: () => api.get(`/v1/chat/rooms/${roomId}/messages?limit=100`),
    enabled: !!roomId && !!user,
    refetchInterval: 5_000,
  });

  useEffect(() => {
    if (messages.data && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.data]);

  const send = useMutation<unknown, ApiError, { body: string }>({
    mutationFn: (b) => api.post(`/v1/chat/rooms/${roomId}/messages`, b),
    onSuccess: () => {
      setDraft("");
      void qc.invalidateQueries({ queryKey: ["chats", "messages", roomId] });
    },
  });

  if (loading || !user || !roomId) {
    return (
      <main className="container mx-auto max-w-3xl px-4 py-12 text-center">
        <p className="text-[var(--color-muted-foreground)]">Loading…</p>
      </main>
    );
  }

  return (
    <main className="container mx-auto flex h-[calc(100vh-3.5rem)] max-w-3xl flex-col px-4 py-4">
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto rounded-md border border-[var(--color-border)] bg-[var(--color-background)] p-4"
        aria-live="polite"
        aria-label="Message history"
      >
        {messages.isLoading && (
          <p className="text-center text-sm text-[var(--color-muted-foreground)]">Loading…</p>
        )}
        {messages.error && (
          <p role="alert" className="text-sm text-[var(--color-destructive)]">
            Failed to load messages: {messages.error.message}
          </p>
        )}
        {messages.data?.items.map((m) => {
          const mine = m.sender_user_id === user.userId;
          return (
            <div
              key={m.id}
              className={`flex ${mine ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[75%] rounded-2xl px-3 py-2 text-sm ${
                  mine
                    ? "bg-[var(--color-brand-primary)] text-[var(--color-primary-foreground)]"
                    : "bg-[var(--color-muted)] text-[var(--color-foreground)]"
                }`}
              >
                <p className="whitespace-pre-wrap break-words">{m.body}</p>
                <p
                  className={`mt-1 text-[10px] ${mine ? "text-white/70" : "text-[var(--color-muted-foreground)]"}`}
                >
                  {new Date(m.created_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) send.mutate({ body: draft.trim() });
        }}
        className="mt-3 flex gap-2"
      >
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message…"
          disabled={send.isPending}
          aria-label="New message"
          className="flex-1"
        />
        <Button type="submit" disabled={send.isPending || !draft.trim()}>
          {send.isPending ? "…" : "Send"}
        </Button>
      </form>
      {send.error && (
        <p role="alert" className="mt-2 text-xs text-[var(--color-destructive)]">
          {send.error.message}
        </p>
      )}
    </main>
  );
}
