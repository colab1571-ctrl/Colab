"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  useAuth,
} from "@colab/ui";

export default function SignupPage(): React.ReactElement {
  const { signUp } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [acceptTos, setAcceptTos] = useState(false);
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [acceptCommunity, setAcceptCommunity] = useState(false);
  const [ageAttestation, setAgeAttestation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit =
    email && password && displayName && acceptTos && acceptPrivacy && acceptCommunity && ageAttestation;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await signUp({
      email,
      password,
      display_name: displayName,
      accept_tos: acceptTos,
      accept_privacy: acceptPrivacy,
      accept_community: acceptCommunity,
      age_attestation: ageAttestation,
    });
    setSubmitting(false);
    if (result.ok) {
      router.push("/discover");
    } else {
      setError(result.error);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12" aria-label="Sign up page">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-semibold">Create your account</h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div>
              <label
                htmlFor="display_name"
                className="text-sm font-medium text-[var(--color-foreground)]"
              >
                Display name
              </label>
              <Input
                id="display_name"
                type="text"
                placeholder="e.g. Maya R."
                className="mt-1"
                autoComplete="nickname"
                required
                minLength={2}
                maxLength={48}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                disabled={submitting}
              />
            </div>
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
                placeholder="At least 10 characters"
                className="mt-1"
                autoComplete="new-password"
                required
                minLength={10}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
              <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
                10+ characters, mix of letters, numbers, and symbols recommended.
              </p>
            </div>

            <fieldset className="space-y-2 pt-2">
              <legend className="text-sm font-medium text-[var(--color-foreground)]">
                Required acknowledgements
              </legend>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={ageAttestation}
                  onChange={(e) => setAgeAttestation(e.target.checked)}
                  className="mt-0.5"
                  disabled={submitting}
                  required
                />
                <span>I confirm I am 18 years of age or older.</span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={acceptTos}
                  onChange={(e) => setAcceptTos(e.target.checked)}
                  className="mt-0.5"
                  disabled={submitting}
                  required
                />
                <span>
                  I have read and accept the{" "}
                  <a
                    href="https://colabclub.net/legal/tos"
                    className="text-[var(--color-brand-primary)] hover:underline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Terms of Service
                  </a>
                  .
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={acceptPrivacy}
                  onChange={(e) => setAcceptPrivacy(e.target.checked)}
                  className="mt-0.5"
                  disabled={submitting}
                  required
                />
                <span>
                  I have read and accept the{" "}
                  <a
                    href="https://colabclub.net/legal/privacy"
                    className="text-[var(--color-brand-primary)] hover:underline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Privacy Policy
                  </a>
                  .
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={acceptCommunity}
                  onChange={(e) => setAcceptCommunity(e.target.checked)}
                  className="mt-0.5"
                  disabled={submitting}
                  required
                />
                <span>
                  I have read and accept the{" "}
                  <a
                    href="https://colabclub.net/legal/community-guidelines"
                    className="text-[var(--color-brand-primary)] hover:underline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Community Guidelines
                  </a>
                  .
                </span>
              </label>
            </fieldset>

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
              disabled={submitting || !canSubmit}
            >
              {submitting ? "Creating account…" : "Create account"}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-[var(--color-muted-foreground)]">
            Already have an account?{" "}
            <a
              href="/login"
              className="text-[var(--color-brand-primary)] hover:underline focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
            >
              Sign in
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
