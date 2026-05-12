"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const CONSENT_KEY = "cookie_consent";

interface ConsentRecord {
  consentVersion: string;
  categories: string[];
  acceptedAt: string;
}

/**
 * Cookie consent banner — "Accept All" only (master spec §0 locked decision).
 * EU/UK dropped from launch geos so GDPR granular consent is not required.
 *
 * On accept:
 *  1. Writes consent record to localStorage.
 *  2. POSTs anonymous audit record to /api/cookie-consent.
 *  3. Initialises PostHog (deferred until consent).
 *
 * Accessibility: role="dialog", aria-label, keyboard-navigable.
 */
export function CookieBanner(): React.ReactElement | null {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(CONSENT_KEY);
      if (!stored) {
        setVisible(true);
      } else {
        // Consent already given — init PostHog
        initPostHog();
      }
    } catch {
      // localStorage unavailable (private browsing edge case) — hide banner
    }
  }, []);

  function initPostHog() {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    const host = process.env.NEXT_PUBLIC_POSTHOG_HOST;
    if (!key) return;
    import("posthog-js").then(({ default: posthog }) => {
      if (!posthog.__loaded) {
        posthog.init(key, {
          api_host: host ?? "https://app.posthog.com",
          capture_pageview: true,
          loaded: () => {/* loaded */},
        });
      }
    });
  }

  async function handleAcceptAll() {
    const record: ConsentRecord = {
      consentVersion: "1",
      categories: ["necessary", "analytics", "functional", "marketing"],
      acceptedAt: new Date().toISOString(),
    };
    try {
      localStorage.setItem(CONSENT_KEY, JSON.stringify(record));
    } catch {
      // ignore
    }
    // Post anonymous audit record — fire-and-forget
    try {
      await fetch("/api/cookie-consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ consentRecord: record }),
      });
    } catch {
      // non-critical
    }
    initPostHog();
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Cookie consent"
      aria-modal="true"
      className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-neutral-200 shadow-lg"
    >
      <div className="max-w-6xl mx-auto px-6 py-4 flex flex-col sm:flex-row items-start sm:items-center gap-4 justify-between">
        <p className="text-sm text-neutral-700 leading-relaxed flex-1">
          We use cookies to improve your experience and analyse usage.
          See our{" "}
          <Link href="/legal/cookies" className="underline hover:text-neutral-900">
            Cookie Policy
          </Link>{" "}
          for details.
        </p>
        <button
          type="button"
          onClick={handleAcceptAll}
          className="btn-primary text-sm shrink-0 focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2"
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus
        >
          Accept All
        </button>
      </div>
    </div>
  );
}
