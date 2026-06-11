"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, useAuth } from "@colab/ui";

export default function LoginPage(): React.ReactElement {
  const { signIn } = useAuth();
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
    setSubmitting(false);
    if (result.ok) {
      router.push("/discover");
    } else {
      setError(result.error);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4" aria-label="Sign in page">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-semibold">Welcome back</h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div>
              <label
                htmlFor="email"
                className="text-sm font-medium text-[var(--color-foreground)]"
              >
                Email address
              </label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                className="mt-1"
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
                htmlFor="password"
                className="text-sm font-medium text-[var(--color-foreground)]"
              >
                Password
              </label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                className="mt-1"
                autoComplete="current-password"
                required
                aria-required="true"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className="flex justify-end">
              <a
                href="/forgot-password"
                className="text-sm text-[var(--color-brand-primary)] hover:underline focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
              >
                Forgot password?
              </a>
            </div>
            {error && (
              <div
                role="alert"
                aria-live="polite"
                className="rounded-md border border-[var(--color-destructive)] bg-[color-mix(in_srgb,var(--color-destructive)_10%,white)] px-3 py-2 text-sm text-[var(--color-destructive)]"
              >
                {error}
              </div>
            )}
            <Button
              className="w-full"
              type="submit"
              disabled={submitting || !email || !password}
            >
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-[var(--color-muted-foreground)]">
            Don&apos;t have an account?{" "}
            <a
              href="/signup"
              className="text-[var(--color-brand-primary)] hover:underline focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
            >
              Sign up
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
