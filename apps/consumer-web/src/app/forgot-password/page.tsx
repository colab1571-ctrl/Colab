"use client";

import React, { useState } from "react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@colab/ui";
import { api, ApiError } from "../../lib/api";

export default function ForgotPasswordPage(): React.ReactElement {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/v1/auth/password/reset/start", { email });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Network error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main
      className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4"
      aria-label="Forgot password page"
    >
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-semibold">Reset your password</h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {done ? (
            <p className="text-sm text-[var(--color-foreground)]">
              If an account exists for <strong>{email}</strong>, we&apos;ve sent a password reset
              link. Check your inbox.
            </p>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div>
                <label htmlFor="email" className="text-sm font-medium">
                  Email address
                </label>
                <Input
                  id="email"
                  type="email"
                  className="mt-1"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={submitting}
                />
              </div>
              {error && (
                <p role="alert" className="text-sm text-[var(--color-destructive)]">
                  {error}
                </p>
              )}
              <Button type="submit" disabled={submitting || !email} className="w-full">
                {submitting ? "Sending…" : "Send reset link"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
