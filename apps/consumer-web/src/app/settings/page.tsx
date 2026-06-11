"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, Card, CardContent, useAuth } from "@colab/ui";
import { api, ApiError } from "../../lib/api";

interface Session {
  id: string;
  user_agent?: string;
  ip?: string;
  last_seen_at?: string;
  created_at?: string;
  is_current?: boolean;
}

export default function SettingsPage(): React.ReactElement {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [sessionsError, setSessionsError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    api
      .get<{ sessions: Session[] }>("/v1/auth/sessions")
      .then((r) => setSessions(r.sessions))
      .catch((e: ApiError) => setSessionsError(e.message));
  }, [user]);

  if (loading || !user) {
    return (
      <main className="container mx-auto max-w-2xl px-4 py-12 text-center">
        <p className="text-[var(--color-muted-foreground)]">Loading…</p>
      </main>
    );
  }

  return (
    <main className="container mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase text-[var(--color-muted-foreground)]">Account</h2>
        <Card className="mt-2">
          <CardContent className="space-y-3 p-4">
            <div>
              <p className="text-xs text-[var(--color-muted-foreground)]">Email</p>
              <p className="font-medium">{user.email}</p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-muted-foreground)]">Tier</p>
              <p className="font-medium capitalize">{user.tier.replace("_", " ")}</p>
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button asChild variant="outline"><Link href="/profile/me">Edit profile</Link></Button>
              <Button variant="outline" asChild><Link href="/forgot-password">Change password</Link></Button>
              {user.tier === "free" && <Button asChild><Link href="/pricing">Upgrade</Link></Button>}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase text-[var(--color-muted-foreground)]">Active sessions</h2>
        <Card className="mt-2">
          <CardContent className="p-4">
            {sessionsError && <p role="alert" className="text-sm text-[var(--color-destructive)]">{sessionsError}</p>}
            {!sessionsError && !sessions && <p className="text-sm text-[var(--color-muted-foreground)]">Loading sessions…</p>}
            {sessions && sessions.length === 0 && <p className="text-sm text-[var(--color-muted-foreground)]">No active sessions.</p>}
            {sessions && sessions.length > 0 && (
              <ul className="space-y-2" role="list">
                {sessions.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border)] p-3 text-sm">
                    <div>
                      <p className="font-medium">
                        {s.user_agent ? truncate(s.user_agent, 40) : "Unknown device"}
                        {s.is_current && <span className="ml-2 text-xs font-normal text-[var(--color-brand-primary)]">(this device)</span>}
                      </p>
                      <p className="text-xs text-[var(--color-muted-foreground)]">
                        {s.ip ?? "—"} · {s.last_seen_at ? `last seen ${new Date(s.last_seen_at).toLocaleString()}` : "never"}
                      </p>
                    </div>
                    {!s.is_current && (
                      <Button variant="outline" type="button" onClick={() => {
                        void api.delete(`/v1/auth/sessions/${s.id}`).then(() => setSessions(sessions.filter((x) => x.id !== s.id))).catch((e: ApiError) => setSessionsError(e.message));
                      }}>Revoke</Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase text-[var(--color-muted-foreground)]">Danger zone</h2>
        <Card className="mt-2 border-[var(--color-destructive)]">
          <CardContent className="space-y-3 p-4">
            <div>
              <p className="font-medium">Sign out everywhere</p>
              <p className="text-sm text-[var(--color-muted-foreground)]">Revokes all sessions on every device.</p>
              <Button variant="outline" className="mt-2" onClick={() => {
                void api.post("/v1/auth/logout/all").then(() => signOut()).then(() => router.push("/")).catch((e: ApiError) => setSessionsError(e.message));
              }}>Sign out everywhere</Button>
            </div>
            <div>
              <p className="font-medium">Delete account</p>
              <p className="text-sm text-[var(--color-muted-foreground)]">Permanently deletes your profile, portfolio, and chat history. Cannot be undone.</p>
              <Button variant="outline" className="mt-2 border-[var(--color-destructive)] text-[var(--color-destructive)]" disabled>
                Delete account (request via support)
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}
