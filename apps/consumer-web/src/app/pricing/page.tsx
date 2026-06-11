import React from "react";
import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { Button, Card, CardContent } from "@colab/ui";

export const metadata: Metadata = {
  title: "Pricing — Colab",
  description:
    "Colab pricing — start free, unlock unlimited collaborations + AI credits with Premium.",
};

interface Tier {
  name: string;
  blurb: string;
  price: string;
  cadence?: string;
  highlight?: boolean;
  features: string[];
  cta: { label: string; href: string };
}

const TIERS: Tier[] = [
  {
    name: "Free",
    blurb: "For exploring the platform.",
    price: "$0",
    features: [
      "30 profile views / day",
      "5 Vibe Checks / week",
      "Unlimited chat with matched collaborators",
      "1 active collab at a time",
      "Standard moderation + safety",
    ],
    cta: { label: "Get started", href: "/signup" },
  },
  {
    name: "Premium",
    blurb: "For active collaborators.",
    price: "$9",
    cadence: "/month",
    highlight: true,
    features: [
      "Unlimited profile views",
      "Unlimited Vibe Checks",
      "Up to 10 active collabs",
      "100 AI credits / month (slash commands)",
      "Hide my profile from non-Premium users",
      "Read receipts + presence",
    ],
    cta: { label: "Start Premium", href: "/signup?plan=premium" },
  },
  {
    name: "Premium Pro",
    blurb: "For working creators + small studios.",
    price: "$19",
    cadence: "/month",
    features: [
      "Everything in Premium",
      "Up to 30 active collabs",
      "500 AI credits / month",
      "Mockup history + export",
      "Whiteboard PDF export",
      "Priority support",
    ],
    cta: { label: "Start Premium Pro", href: "/signup?plan=premium_pro" },
  },
];

export default function PricingPage(): React.ReactElement {
  return (
    <main className="container mx-auto max-w-6xl px-4 py-12">
      <section className="mx-auto max-w-2xl text-center">
        <h1 className="text-4xl font-bold tracking-tight">Pricing</h1>
        <p className="mt-3 text-base text-[var(--color-muted-foreground)]">
          Start free. Upgrade when you need unlimited collaborations and AI tools.
        </p>
      </section>

      <ul
        className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3"
        role="list"
        aria-label="Pricing tiers"
      >
        {TIERS.map((tier) => (
          <li key={tier.name}>
            <Card
              className={
                tier.highlight
                  ? "h-full border-[var(--color-brand-primary)] shadow-lg"
                  : "h-full"
              }
            >
              <CardContent className="flex h-full flex-col p-6">
                {tier.highlight && (
                  <p className="mb-3 inline-flex w-fit rounded-full bg-[var(--color-brand-primary)] px-2.5 py-0.5 text-xs font-medium text-[var(--color-primary-foreground)]">
                    Most popular
                  </p>
                )}
                <h2 className="text-xl font-semibold">{tier.name}</h2>
                <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">{tier.blurb}</p>
                <p className="mt-4 flex items-baseline gap-1">
                  <span className="text-3xl font-bold">{tier.price}</span>
                  {tier.cadence && (
                    <span className="text-sm text-[var(--color-muted-foreground)]">
                      {tier.cadence}
                    </span>
                  )}
                </p>
                <ul className="mt-6 flex-1 space-y-2" role="list">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <span
                        aria-hidden="true"
                        className="mt-1 inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-brand-primary)_15%,transparent)] text-[var(--color-brand-primary)]"
                      >
                        ✓
                      </span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-6">
                  <Button asChild className="w-full">
                    <Link href={tier.cta.href as Route}>{tier.cta.label}</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>

      <section className="mx-auto mt-16 max-w-3xl text-center">
        <h2 className="text-2xl font-semibold">Frequently asked</h2>
        <dl className="mt-6 grid grid-cols-1 gap-6 text-left sm:grid-cols-2">
          <div>
            <dt className="font-semibold">Can I cancel any time?</dt>
            <dd className="mt-1 text-sm text-[var(--color-muted-foreground)]">
              Yes — cancel from Settings any time. Mobile subscriptions are managed through Apple
              or Google. 14-day refund on the web.
            </dd>
          </div>
          <div>
            <dt className="font-semibold">How do AI credits work?</dt>
            <dd className="mt-1 text-sm text-[var(--color-muted-foreground)]">
              Each AI slash command (mockup, song concept, brief) costs a small fixed amount of
              credits. Unused credits roll over month-to-month, up to 2× your monthly grant.
            </dd>
          </div>
          <div>
            <dt className="font-semibold">Where&apos;s the free tier limit?</dt>
            <dd className="mt-1 text-sm text-[var(--color-muted-foreground)]">
              30 profile views per day and 5 Vibe Checks per week. We&apos;ll show you a banner
              when you&apos;re close.
            </dd>
          </div>
          <div>
            <dt className="font-semibold">Is there an annual discount?</dt>
            <dd className="mt-1 text-sm text-[var(--color-muted-foreground)]">
              Coming during early access. We&apos;ll email everyone on the waitlist with the
              launch promo.
            </dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
