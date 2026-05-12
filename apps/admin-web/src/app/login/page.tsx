import React from "react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@colab/ui";

export default function AdminLoginPage(): React.ReactElement {
  return (
    <main
      className="flex min-h-screen items-center justify-center bg-neutral-100 px-4"
      aria-label="Admin Console sign-in page"
    >
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-semibold">Admin Console</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p
            className="text-sm text-[var(--color-muted-foreground)]"
            role="note"
            aria-label="Access requirement"
          >
            IP-allowlisted + admin role required.
          </p>
          <div>
            <label
              htmlFor="admin-email"
              className="block text-sm font-medium text-[var(--color-foreground)] mb-1"
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
            />
          </div>
          <div>
            <label
              htmlFor="admin-password"
              className="block text-sm font-medium text-[var(--color-foreground)] mb-1"
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
            />
          </div>
          <div
            id="admin-login-status"
            role="status"
            aria-live="polite"
            className="sr-only"
          />
          <Button
            className="w-full"
            type="submit"
            aria-describedby="admin-login-status"
          >
            Sign in
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
