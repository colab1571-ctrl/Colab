import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../lib/brand";
import { WaitlistForm } from "../../components/WaitlistForm";

export const metadata: Metadata = {
  title: `How ${BRAND_NAME} Works`,
  description: `Learn how ${BRAND_NAME} uses AI to match artists and creators for real collaboration — from profile setup to your first creative project.`,
  alternates: { canonical: `${SITE_URL}/how-it-works` },
  openGraph: {
    title: `How ${BRAND_NAME} Works`,
    description: `AI-powered artist matching in three steps.`,
    url: `${SITE_URL}/how-it-works`,
    images: [{ url: "/og/how-it-works.png", width: 1200, height: 630 }],
  },
  twitter: {
    title: `How ${BRAND_NAME} Works`,
    description: "AI-powered artist matching in three steps.",
    images: ["/og/how-it-works.png"],
  },
};

const steps = [
  {
    step: "01",
    title: "Build your creative profile",
    description: [
      `Create your ${BRAND_NAME} profile in minutes. Upload up to 12 portfolio items (images, audio, video), choose your vocation categories, write a short bio and "obsessed with" blurb, and set your collaboration radius.`,
      "No follower counts are displayed. No engagement metrics. Just your work.",
    ],
    details: [
      "9 creative vocation categories + sub-tags",
      "Portfolio: up to 12 items, 10 MB images / 30 MB audio / 100 MB video",
      "Optional: connect Instagram, YouTube, or Spotify for Artists",
      "Optional: take a 5-question personality quiz to improve matching accuracy",
    ],
  },
  {
    step: "02",
    title: "Get matched by AI",
    description: [
      `${BRAND_NAME}'s matching engine generates embeddings from your portfolio and creative profile, then finds collaborators with complementary skills and compatible creative vision.`,
      `Daily "Picked for You" recommendations surface the most relevant matches. Browse and filter at your own pace — by vocation, location, experience, or open-to-remote preference.`,
    ],
    details: [
      "AI ranking: portfolio similarity + complementary skills + recent activity",
      "Daily curated picks + free-browse with filters",
      "Save profiles privately; no one is notified",
      `Free tier: 30 profiles/day · Premium: unlimited`,
    ],
  },
  {
    step: "03",
    title: "Vibe Check — your collaboration proposal",
    description: [
      `Found someone interesting? Send them a Vibe Check — a 250-character brief describing the collab you have in mind. Focused, intentional, no spam.`,
      "If they accept, a private workspace opens instantly. If they decline or don't respond within 30 days, the request expires quietly.",
    ],
    details: [
      "250-character max synopsis — keeps proposals focused",
      "No notification to the recipient if you decline (mutual respect)",
      "30-day TTL on unanswered requests",
      "Free: 5 Vibe Checks / week · Premium: unlimited",
    ],
  },
  {
    step: "04",
    title: "Create together in your workspace",
    description: [
      `Every accepted match gets a private workspace with everything you need to collaborate: real-time chat, file sharing, a project plan, a virtual whiteboard (tldraw), and optional Google Meet scheduling.`,
      "All files are version-tracked for IP safety. AI tools — mockup generation, chat summarization, brainstorming — are available to Premium members with mutual consent.",
    ],
    details: [
      "Real-time chat + file sharing (image / audio / video / docs)",
      "Built-in project plan: tasks, owners, due dates",
      "Virtual whiteboard powered by tldraw",
      "AI commands: /mockup-image, /mockup-audio, /summarize-chat, /brainstorm, /palette",
    ],
  },
];

export default function HowItWorksPage(): React.ReactElement {
  return (
    <>
      <section className="max-w-4xl mx-auto px-6 py-16 text-center">
        <p className="text-sm font-semibold uppercase tracking-widest text-[var(--color-brand-primary)] mb-4">
          The process
        </p>
        <h1 className="text-5xl font-bold text-neutral-900 mb-6">
          How {BRAND_NAME} works
        </h1>
        <p className="text-xl text-neutral-500 max-w-2xl mx-auto">
          From profile to creative partnership — here&apos;s what the journey looks like.
        </p>
      </section>

      <section className="max-w-4xl mx-auto px-6 pb-20">
        <ol className="space-y-20 list-none m-0 p-0">
          {steps.map(({ step, title, description, details }) => (
            <li key={step} className="grid md:grid-cols-[auto_1fr] gap-8 items-start">
              <div
                className="text-6xl font-black leading-none shrink-0 hidden md:block"
                style={{ color: "var(--color-brand-secondary)" }}
                aria-label={`Step ${step}`}
              >
                {step}
              </div>
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <span
                    className="text-2xl font-black md:hidden"
                    style={{ color: "var(--color-brand-secondary)" }}
                    aria-hidden="true"
                  >
                    {step}
                  </span>
                  <h2 className="text-2xl font-bold text-neutral-900">
                    {title}
                  </h2>
                </div>
                {description.map((para, i) => (
                  <p key={i} className="text-neutral-600 leading-relaxed mb-4">
                    {para}
                  </p>
                ))}
                <ul className="mt-4 space-y-2 list-none m-0 p-0">
                  {details.map((detail) => (
                    <li
                      key={detail}
                      className="flex items-start gap-2 text-sm text-neutral-500"
                    >
                      <span
                        className="shrink-0 font-bold"
                        style={{ color: "var(--color-brand-primary)" }}
                        aria-hidden="true"
                      >
                        ✓
                      </span>
                      {detail}
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Animated diagram placeholder */}
      <div
        className="max-w-4xl mx-auto px-6 pb-12"
        aria-label="Platform diagram — coming at Phase 5 design pass"
      >
        <div className="bg-neutral-50 border border-dashed border-neutral-200 rounded-2xl p-16 text-center text-neutral-400 text-sm">
          [Platform flow diagram — Phase 5 design pass]
        </div>
      </div>

      {/* CTA */}
      <section className="py-20 px-6 text-center bg-neutral-50">
        <div className="max-w-xl mx-auto">
          <h2 className="text-3xl font-bold text-neutral-900 mb-4">
            Ready to try it?
          </h2>
          <p className="text-neutral-500 mb-8">
            Join the waitlist and be among the first creators on {BRAND_NAME}.
          </p>
          <WaitlistForm source="how-it-works" />
        </div>
      </section>
    </>
  );
}
