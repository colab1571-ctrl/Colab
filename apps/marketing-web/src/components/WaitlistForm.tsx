"use client";

import { useState, useId } from "react";

type FormState = "idle" | "loading" | "success" | "duplicate" | "error";

/**
 * Waitlist email capture form.
 * - Validates email client-side before submit.
 * - Shows CASL consent checkbox (displayed for all visitors; required for CA).
 * - POST /api/waitlist → 201 success | 409 duplicate | 422 invalid | 500 error.
 * - Accessible: labelled inputs, aria-live feedback region.
 */
export function WaitlistForm({ source = "homepage" }: { source?: string }): React.ReactElement {
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<FormState>("idle");
  const emailId = useId();
  const consentId = useId();
  const statusId = useId();

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!email) return;
    setState("loading");

    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          source,
          consentAt: consent ? new Date().toISOString() : undefined,
        }),
      });

      if (res.status === 201) {
        setState("success");
      } else if (res.status === 409) {
        setState("duplicate");
      } else if (res.status === 422) {
        setState("error");
      } else {
        setState("error");
      }
    } catch {
      setState("error");
    }
  }

  if (state === "success") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="text-center py-6"
      >
        <p className="text-lg font-semibold text-green-700">
          You&apos;re on the list!
        </p>
        <p className="text-sm text-neutral-500 mt-1">
          We&apos;ll email you when we launch. Check your inbox for confirmation.
        </p>
      </div>
    );
  }

  if (state === "duplicate") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="text-center py-6"
      >
        <p className="text-lg font-semibold text-neutral-800">
          Already on the list!
        </p>
        <p className="text-sm text-neutral-500 mt-1">
          You&apos;re already signed up. We&apos;ll be in touch soon.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 w-full max-w-md mx-auto"
      aria-describedby={statusId}
      noValidate
    >
      <div className="flex flex-col sm:flex-row gap-3">
        <label htmlFor={emailId} className="sr-only">
          Email address
        </label>
        <input
          id={emailId}
          type="email"
          name="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="your@email.com"
          autoComplete="email"
          className="flex-1 px-4 py-3 border border-neutral-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)] focus:border-transparent disabled:opacity-60"
          disabled={state === "loading"}
          aria-describedby={statusId}
          aria-required="true"
          aria-invalid={state === "error" ? "true" : undefined}
        />
        <button
          type="submit"
          disabled={state === "loading" || !email}
          className="btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {state === "loading" ? "Joining…" : "Join waitlist"}
        </button>
      </div>

      {/* CASL consent checkbox — displayed for all visitors */}
      <div className="flex items-start gap-2 text-left">
        <input
          id={consentId}
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-neutral-300 text-[var(--color-brand-primary)] focus:ring-[var(--color-brand-primary)]"
          aria-describedby={`${consentId}-desc`}
        />
        <div>
          <label
            htmlFor={consentId}
            className="text-xs text-neutral-600 cursor-pointer"
          >
            I agree to receive launch updates and marketing emails. I can
            unsubscribe any time.
          </label>
          <p id={`${consentId}-desc`} className="text-xs text-neutral-400 mt-0.5">
            Required for Canadian residents (CASL).
          </p>
        </div>
      </div>

      {/* Feedback region */}
      <div id={statusId} aria-live="polite" role="status">
        {state === "error" && (
          <p className="text-sm text-red-600">
            Something went wrong. Please check your email and try again.
          </p>
        )}
      </div>

      <p className="text-xs text-neutral-400 text-center">
        US, CA, AU, NZ, IN · 18+ only · No spam
      </p>
    </form>
  );
}
