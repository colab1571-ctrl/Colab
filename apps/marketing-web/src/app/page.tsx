/**
 * Marketing landing page — placeholder with waitlist email form stub.
 * Full build in spec 017 (marketing-web).
 */

import { Button } from "@colab/ui";

export default function LandingPage(): React.ReactElement {
  return (
    <main>
      {/* Nav */}
      <nav className="border-b border-neutral-100 px-6 py-4 flex items-center justify-between">
        <span className="text-xl font-bold" style={{ color: "var(--color-brand-primary)" }}>
          Colab
        </span>
        <div className="flex items-center gap-6">
          <a href="/pricing" className="text-sm text-neutral-600 hover:text-neutral-900">
            Pricing
          </a>
          <a href="/about" className="text-sm text-neutral-600 hover:text-neutral-900">
            About
          </a>
          <Button asChild size="sm">
            <a href="https://app.colab.app">Get started</a>
          </Button>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 py-24 text-center">
        <h1 className="text-5xl md:text-6xl font-bold text-neutral-900 mb-6 leading-tight">
          Create together.{" "}
          <span style={{ color: "var(--color-brand-primary)" }}>Actually.</span>
        </h1>
        <p className="text-xl text-neutral-500 mb-10 max-w-2xl mx-auto">
          Colab connects rising artists and creators for real creative partnerships — not follower counts.
        </p>

        {/* Waitlist form stub — full implementation in spec 017 */}
        <form
          action="/api/waitlist"
          method="POST"
          className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto"
        >
          <input
            type="email"
            name="email"
            required
            placeholder="your@email.com"
            className="flex-1 px-4 py-3 border border-neutral-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)]"
          />
          <button
            type="submit"
            className="px-6 py-3 bg-[var(--color-brand-primary)] text-white rounded-xl font-semibold text-sm hover:opacity-90 transition-opacity"
          >
            Join waitlist
          </button>
        </form>
        <p className="text-xs text-neutral-400 mt-4">
          US, CA, AU, NZ, IN · 18+ only · No spam
        </p>
      </section>

      {/* Features section (placeholder) */}
      <section className="bg-neutral-50 py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-sm font-medium uppercase tracking-wide text-neutral-400 mb-2">
            Coming in spec 017
          </p>
          <h2 className="text-3xl font-bold text-neutral-900">Full marketing site</h2>
        </div>
      </section>
    </main>
  );
}
