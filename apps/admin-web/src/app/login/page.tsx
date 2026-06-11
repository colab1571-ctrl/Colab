"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, useAuth } from "@colab/ui";

const ADMIN_ROLES = ["super_admin", "mod", "support", "billing_admin", "auditor"] as const;

export default function AdminLoginPage(): React.ReactElement {
  const { signIn, signOut } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await signIn({ email, password });
    if (!result.ok) {
      setSubmitting(false);
      setError(result.error);
      return;
    }

    // signIn() refreshes the user behind the scenes. Pull the latest user
    // payload from /v1/auth/me directly so we don't race React state.
    let roles: string[] = [];
    try {
      const token =
        typeof window !== "undefined"
          ? window.localStorage.getItem("colab:access_token")
          : null;
      if (token) {
        const resp = await fetch("/v1/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
          credentials: "include",
        });
        if (resp.ok) {
          const me = (await resp.json()) as { roles?: string[] };
          roles = Array.isArray(me.roles) ? me.roles : [];
        }
      }
    } catch {
      // Fall through — roles stays [] and we'll reject below.
    }

    const hasAdminRole = roles.some((r) => (ADMIN_ROLES as readonly string[]).includes(r));
    if (!hasAdminRole) {
      // Sign the user back out so a non-admin can't sit in a logged-in state
      // staring at /login.
      await signOut();
      setSubmitting(false);
      setError("You do not have admin access.");
      return;
    }

    setSubmitting(false);
    router.push("/dashboard");
  };

  return (
    <main
      className="flex min-h-screen items-center justify-center bg-neutral-50 px-4"
      aria-label="Admin Console sign-in page"
    >
      <Card className="w-full max-w-sm border-neutral-200 bg-white">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-semibold text-neutral-900">Admin Console</h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="mb-4 text-sm text-neutral-500"
            role="note"
            aria-label="Access requirement"
          >
            IP-allowlisted + admin role required.
          </p>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div>
              <label
                htmlFor="admin-email"
                className="block text-sm font-medium text-neutral-900 mb-1"
              >
                Admin email
              </label>
              <Input
                id="admin-email"
                type="email"
                placeholder="admin@colab.app"
                autoComplete="email"
                required
                aria-required="true"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div>
              <label
                htmlFor="admin-password"
                className="block text-sm font-medium text-neutral-900 mb-1"
              >
                Password
              </label>
              <Input
                id="admin-password"
                type="password"
                placeholder="••••••••"
                autoComplete="current-password"
                required
                aria-required="true"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
            </div>
            {error && (
              <div
                role="alert"
                aria-live="polite"
                className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
              >
                {error}
              </div>
            )}
            <div
              id="admin-login-status"
              role="status"
              aria-live="polite"
              className="sr-only"
            >
              {submitting ? "Signing in" : ""}
            </div>
            <Button
              className="w-full"
              type="submit"
              aria-describedby="admin-login-status"
              disabled={submitting || !email || !password}
            >
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <p className="mt-4 text-center text-xs text-neutral-400">
            Admin accounts are provisioned by super_admin. No self sign-up.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
