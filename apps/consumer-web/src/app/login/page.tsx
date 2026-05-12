import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@colab/ui";
import React from "react";

export default function LoginPage(): React.ReactElement {
  return (
    <main className="flex min-h-screen items-center justify-center px-4" aria-label="Sign in page">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-semibold">Welcome back</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
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
              aria-describedby="email-hint"
            />
            <p id="email-hint" className="sr-only">Enter your Colab account email address</p>
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
          <div
            id="login-status"
            role="status"
            aria-live="polite"
            className="sr-only"
          />
          <Button
            className="w-full"
            type="submit"
            aria-describedby="login-status"
          >
            Sign in
          </Button>
          <p className="text-center text-sm text-[var(--color-muted-foreground)]">
            Don&apos;t have an account?{" "}
            <a
              href="/signup"
              className="text-[var(--color-brand-primary)] hover:underline focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
            >
              Sign up
            </a>
          </p>
          <p className="text-center text-xs text-[var(--color-muted-foreground)]">
            Full auth flow implemented in P2 (auth-svc).
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
