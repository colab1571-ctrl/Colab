import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../lib/brand";
import { WaitlistForm } from "../components/WaitlistForm";
import { AppStoreBadges } from "../components/AppStoreBadges";

export const metadata: Metadata = {
  title: `${BRAND_NAME} — Find Your Creative Co-Founder`,
  description:
    "AI-powered networking and collaboration for artists and creators. No follower counts, no engagement farming — just real creative output.",
  alternates: { canonical: SITE_URL },
  openGraph: {
    title: `${BRAND_NAME} — Find Your Creative Co-Founder`,
    description:
      "AI-powered networking and collaboration for artists and creators. Stop scrolling, start making.",
    url: SITE_URL,
    images: [{ url: "/og/home.png", width: 1200, height: 630 }],
  },
  twitter: {
    title: `${BRAND_NAME} — Find Your Creative Co-Founder`,
    description:
      "AI-powered networking and collaboration for artists and creators.",
    images: ["/og/home.png"],
  },
};

const valueProps = [
  {
    icon: "✦",
    heading: "Real Collaboration, Not Content",
    body: `${BRAND_NAME} is built for artists who want creative partners, not more followers. We optimize for creative output, not time-on-app.`,
  },
  {
    icon: "◈",
    heading: "AI-Powered Matching",
    body: "Our matching engine reads your portfolio and creative DNA to surface the right co-founders — complementary skills, compatible vision.",
  },
  {
    icon: "◎",
    heading: "Safe & IP-Protected",
    body: "Built-in project workspaces, IP-safe audit logs, and mutual-consent AI tools. Your work is your work.",
  },
];

const howItWorksSteps = [
  {
    step: "01",
    title: "Build your creative profile",
    description:
      "Upload your portfolio, describe your vocation, and share what you're looking for in a collaborator. No follower counts displayed.",
  },
  {
    step: "02",
    title: "Get matched by AI",
    description: `${BRAND_NAME}'s matching engine finds creators with complementary skills and compatible creative vision. Daily curated picks, plus browse at your own pace.`,
  },
  {
    step: "03",
    title: "Create together",
    description:
      "Send a Vibe Check, start a private workspace, share files, and collaborate with all the tools you need — chat, whiteboard, project plan, and more.",
  },
];

const faqTeaser = [
  {
    q: "Is it free?",
    a: `${BRAND_NAME} offers a free tier. Premium plans unlock unlimited connections, AI credits, and more.`,
  },
  {
    q: "What types of creators are on the platform?",
    a: "Visual artists, musicians, designers, filmmakers, writers, and more — across 9 creative vocation categories.",
  },
];

export default function HomePage(): React.ReactElement {
  return (
    <>
      {/* ─── Hero ─── */}
      <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
        <p className="text-sm font-semibold uppercase tracking-widest text-[var(--color-brand-primary)] mb-4">
          Artist networking, reimagined
        </p>
        <h1 className="text-5xl md:text-6xl font-bold text-neutral-900 mb-6 leading-tight tracking-tight">
          Find your creative{" "}
          <span style={{ color: "var(--color-brand-primary)" }}>co-founder.</span>
        </h1>
        <p className="text-xl text-neutral-500 mb-8 max-w-2xl mx-auto leading-relaxed">
          {BRAND_NAME} connects artists and creators for real collaboration —
          no follower counts, no engagement farming, just creative output.
          Available on iOS and Android.
        </p>

        <div className="flex flex-col items-center gap-6">
          <div id="waitlist" className="w-full max-w-md mx-auto scroll-mt-24">
            <WaitlistForm source="homepage-hero" />
          </div>
          <AppStoreBadges className="justify-center" />
        </div>

        {/* Anti-pattern framing */}
        <p className="mt-12 text-sm text-neutral-400 max-w-lg mx-auto">
          We don&apos;t show you ads. We don&apos;t measure your time-on-app.
          We optimize for one thing: real creative output.
        </p>
      </section>

      {/* ─── Value Props ─── */}
      <section
        className="bg-neutral-50 py-20 px-6"
        aria-labelledby="value-props-heading"
      >
        <div className="max-w-5xl mx-auto">
          <h2
            id="value-props-heading"
            className="text-3xl font-bold text-center text-neutral-900 mb-12"
          >
            Built different, by design
          </h2>
          <ul className="grid grid-cols-1 md:grid-cols-3 gap-8 list-none m-0 p-0">
            {valueProps.map(({ icon, heading, body }) => (
              <li
                key={heading}
                className="bg-white rounded-2xl p-8 shadow-sm border border-neutral-100"
              >
                <span
                  className="text-3xl mb-4 block"
                  aria-hidden="true"
                  style={{ color: "var(--color-brand-primary)" }}
                >
                  {icon}
                </span>
                <h3 className="text-lg font-bold text-neutral-900 mb-2">
                  {heading}
                </h3>
                <p className="text-neutral-500 text-sm leading-relaxed">{body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ─── How It Works (preview) ─── */}
      <section
        className="py-20 px-6"
        aria-labelledby="how-it-works-heading"
      >
        <div className="max-w-4xl mx-auto">
          <h2
            id="how-it-works-heading"
            className="text-3xl font-bold text-center text-neutral-900 mb-4"
          >
            How {BRAND_NAME} works
          </h2>
          <p className="text-center text-neutral-500 mb-12 max-w-xl mx-auto">
            Three steps from sign-up to your first creative collab.
          </p>
          <ol className="space-y-8 list-none m-0 p-0">
            {howItWorksSteps.map(({ step, title, description }) => (
              <li key={step} className="flex gap-6 items-start">
                <span
                  className="text-4xl font-black shrink-0 leading-none mt-1"
                  style={{ color: "var(--color-brand-secondary)" }}
                  aria-label={`Step ${step}`}
                >
                  {step}
                </span>
                <div>
                  <h3 className="text-xl font-bold text-neutral-900 mb-2">
                    {title}
                  </h3>
                  <p className="text-neutral-500 leading-relaxed">
                    {description}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <div className="text-center mt-12">
            <a href="/how-it-works" className="btn-secondary inline-block">
              Learn more about how it works →
            </a>
          </div>
        </div>
      </section>

      {/* ─── Testimonials placeholder ─── */}
      <section
        className="bg-neutral-50 py-20 px-6"
        aria-labelledby="testimonials-heading"
      >
        <div className="max-w-5xl mx-auto text-center">
          <h2
            id="testimonials-heading"
            className="text-3xl font-bold text-neutral-900 mb-4"
          >
            What creators are saying
          </h2>
          <p className="text-neutral-400 text-sm">
            [Testimonials — populated at Phase 5 design pass and launch]
          </p>
        </div>
      </section>

      {/* ─── FAQ Teaser ─── */}
      <section className="py-20 px-6" aria-labelledby="faq-teaser-heading">
        <div className="max-w-3xl mx-auto">
          <h2
            id="faq-teaser-heading"
            className="text-3xl font-bold text-neutral-900 mb-8 text-center"
          >
            Common questions
          </h2>
          <dl className="space-y-6">
            {faqTeaser.map(({ q, a }) => (
              <div key={q} className="border-b border-neutral-100 pb-6">
                <dt className="font-semibold text-neutral-900 mb-2">{q}</dt>
                <dd className="text-neutral-500 leading-relaxed">{a}</dd>
              </div>
            ))}
          </dl>
          <div className="text-center mt-10">
            <a href="/faq" className="btn-secondary inline-block">
              See all FAQs →
            </a>
          </div>
        </div>
      </section>

      {/* ─── Bottom CTA ─── */}
      <section
        className="py-20 px-6 text-center"
        aria-labelledby="cta-heading"
        style={{ background: "var(--color-brand-primary)" }}
      >
        <div className="max-w-2xl mx-auto">
          <h2
            id="cta-heading"
            className="text-3xl md:text-4xl font-bold text-white mb-4"
          >
            Ready to find your creative co-founder?
          </h2>
          <p className="text-white/80 mb-8">
            Join the waitlist. We launch in the US, CA, AU, NZ, and IN. 18+ only.
          </p>
          <div className="max-w-md mx-auto">
            <WaitlistForm source="homepage-cta" />
          </div>
        </div>
      </section>
    </>
  );
}
