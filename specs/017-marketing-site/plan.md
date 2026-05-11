# Plan — 017 Marketing Site (`marketing-web`)

> Status: **DRAFT — ready for Phase 5 design pass**.
> Phase: P16 (runs after P15 Admin Console; blocked by 002 Shared Platform design tokens).
> Last updated: 2026-05-11.

---

## 1. Mission Recap

Build the leading AI-powered networking and collaboration platform for rising artists and creators in the gig economy — low-friction, anti-engagement-farming, productive-partnerships-first.

The marketing site is the **public face** of that mission. Its sole jobs are:

1. Communicate the value proposition to artists and creators landing from organic search, social share, or app-store redirect.
2. Capture signup intent (waitlist email) before the app launches.
3. Surface every legal document required at sign-up (ToS, Privacy, Community Guidelines, DMCA, Cookies).
4. Drive installs with App Store / Play Store badges once the stores go live.

This plan covers only `apps/marketing-web` — the static-export Next.js app deployed to CloudFront (ARC-22). It does **not** touch the consumer-web or admin-console Next.js apps.

---

## 2. Research Notes

### 2.1 Next.js 15 App Router

- Use the **App Router** (`app/` directory) exclusively. Pages Router is not adopted.
- Static export via `output: 'export'` in `next.config.ts` — renders every page to HTML at build time.
- No server-side rendering at runtime; all dynamic behavior is client-side or handled by the standalone Next.js route handler (waitlist API, see §2.6).
- The waitlist `POST /api/waitlist` route handler is **not** statically exported — it runs as a Lambda@Edge or a lightweight Fargate task behind the same CloudFront distribution. Alternatively it is proxied through the gateway service (ARC-3). Decision deferred to infrastructure team; the route handler contract is fixed regardless.
- Image optimization: `next/image` with `unoptimized: false` is incompatible with pure static export. Use `loader: 'custom'` pointing at CloudFront image URLs, **or** pre-optimize images at build time via `sharp` script and store in `public/`. Chosen approach: build-time optimization with `sharp` + CloudFront serving.

### 2.2 MDX Content via `@next/mdx`

- Install: `@next/mdx`, `@mdx-js/react`, `remark-gfm`, `rehype-slug`, `rehype-autolink-headings`.
- Configure in `next.config.ts`:

  ```ts
  import createMDX from '@next/mdx'
  const withMDX = createMDX({ options: { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeSlug] } })
  export default withMDX(nextConfig)
  ```

- Legal pages and blog posts live in `apps/marketing-web/content/` as `.mdx` files.
- A shared `<MDXLayout>` component wraps all content pages with consistent nav + footer.
- MDX frontmatter (`title`, `description`, `lastUpdated`, `ogTitle`, `ogDescription`) drives per-page `<Metadata>`.

### 2.3 Static Export and CloudFront Cache-Control

- Build output: `out/` directory, uploaded to S3 via `aws s3 sync --delete`.
- CloudFront distribution in front of S3. Origin is the S3 bucket (OAC, no public bucket ACL).
- Cache-control headers set via CloudFront response headers policy (not S3 metadata):

  | Path pattern | `Cache-Control` |
  |---|---|
  | `/_next/static/*` | `public, max-age=31536000, immutable` |
  | `/fonts/*`, `/images/*` | `public, max-age=2592000` (30 days) |
  | `/*.html`, `/` | `public, max-age=0, s-maxage=86400, stale-while-revalidate=3600` |
  | `/sitemap.xml`, `/robots.txt` | `public, max-age=3600` |
  | `/api/*` | `no-store` |

- CloudFront invalidation (`/*`) triggered on every deploy via GitHub Actions.
- All HTML pages also served with `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin` via response headers policy.

### 2.4 OG Image Generation via `@vercel/og`

- `@vercel/og` (now `next/og`) generates opengraph images at the **Edge** runtime.
- Because we static-export, OG images for pages with known metadata are **pre-generated** at build time using a `scripts/generate-og.ts` script (calls the same `ImageResponse` API, writes PNGs to `public/og/`).
- Dynamic OG images (blog slugs) use the same script seeded from MDX frontmatter at build time.
- Each page's `<Metadata>` references `{ openGraph: { images: ['/og/<page-slug>.png'] } }`.
- OG image dimensions: 1200×630. Font: system Inter fallback until brand typeface is locked.

### 2.5 Sitemap via `next-sitemap`

- Install: `next-sitemap`.
- `next-sitemap.config.js` generates `sitemap.xml` + `robots.txt` as a `postbuild` npm script.
- Config:

  ```js
  module.exports = {
    siteUrl: process.env.NEXT_PUBLIC_SITE_URL,
    generateRobotsTxt: true,
    changefreq: 'weekly',
    priority: 0.7,
    exclude: ['/api/*'],
    additionalPaths: async () => [
      { loc: '/blog', priority: 0.8 },  // reserved even before blog ships
    ],
  }
  ```

- Blog slug pages use `additionalPaths` fed from MDX content directory scan.
- `robots.txt` disallows `/api/` and allows all crawlers for everything else.

### 2.6 Structured Data (JSON-LD)

Three schemas implemented across the site:

- **Organization** (rendered in `app/layout.tsx` for global presence):

  ```json
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "<BRAND_NAME>",
    "url": "https://<DOMAIN>",
    "logo": "https://<DOMAIN>/images/logo.png",
    "sameAs": ["<INSTAGRAM_URL>", "<TWITTER_URL>"]
  }
  ```

- **WebSite** (also in `app/layout.tsx`, enables sitelinks search box potential):

  ```json
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": "<BRAND_NAME>",
    "url": "https://<DOMAIN>",
    "potentialAction": {
      "@type": "SearchAction",
      "target": "https://<DOMAIN>/search?q={search_term_string}",
      "query-input": "required name=search_term_string"
    }
  }
  ```

- **FAQPage** (rendered on `/faq` only):

  ```json
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      { "@type": "Question", "name": "...", "acceptedAnswer": { "@type": "Answer", "text": "..." } }
    ]
  }
  ```

All JSON-LD is injected via Next.js `<Script id="ld-json" type="application/ld+json">` in the relevant layout or page file.

### 2.7 AWS SES List Integration for Waitlist

- `POST /api/waitlist` route handler:
  1. Validate email (regex + `zod`).
  2. Check for duplicate in `WaitlistEmail` table via Postgres (via gateway → `notification-svc` or a lightweight direct query — implementation detail deferred).
  3. Call `SES.createContact` on the SES contact list configured for waitlist marketing.
  4. Write `WaitlistEmail` row: `{ id, email, source, created_at, ip_hashed }`.
  5. Return `{ ok: true }` or structured error.
- SES list name: `WAITLIST_LIST_NAME` env var.
- Rate-limit: 5 requests / IP / hour (handled at API Gateway / gateway service layer).
- Confirmation email: SES template `waitlist-confirm` sent to user; double-opt-in **not** required for US/CA/AU/NZ (CAN-SPAM + CASL single opt-in is sufficient with unsubscribe link).
- CASL (Canada) compliance: explicit consent checkbox on form, stored in `WaitlistEmail.consent_at`.

---

## 3. Page List

| Route | Title | Notes |
|---|---|---|
| `/` | `<BRAND_NAME> — Find Your Creative Co-Founder` | Hero + value props + "how it works" preview + testimonials placeholder + FAQ teaser + CTA + app badges + footer |
| `/how-it-works` | `How <BRAND_NAME> Works` | 3-step detailed breakdown + animated diagram placeholder |
| `/faq` | `FAQ — <BRAND_NAME>` | Full FAQ, FAQPage JSON-LD, searchable client-side filter |
| `/about` | `About <BRAND_NAME>` | Mission / team placeholder / values |
| `/legal/tos` | `Terms of Service` | MDX, `lastUpdated` frontmatter |
| `/legal/privacy` | `Privacy Policy` | MDX, `lastUpdated` frontmatter |
| `/legal/community-guidelines` | `Community Guidelines` | MDX |
| `/legal/dmca` | `DMCA Notice & Takedown Policy` | MDX, agent-deferred status noted inline |
| `/legal/cookies` | `Cookie Policy` | MDX |
| `/blog/[slug]` | `(deferred — route reserved)` | Route exists; renders 404 or redirect until blog ships in v1.1. MDX reader already wired. |

**Note**: `/blog` index page renders a "Coming soon" stub so the route is not a dead 404. The `[slug]` dynamic route returns a static 404 shell until content is added.

---

## 4. Hero Copy Framework

> Brand voice is pending the Phase 5 ui-ux-pro-max design pass. All copy below ships with `<BRAND_NAME>` tokens and neutral placeholder text. Copywriter replaces tokens before launch.

### Headline options (ship token, pick one at design pass)

```
<BRAND_NAME> — Find Your Creative Co-Founder.
Stop scrolling, start making.
Your next collab is one Vibe Check away.
The anti-algorithm platform for artists who want to create, not perform.
```

### Sub-headline (placeholder)

```
<BRAND_NAME> connects artists and creators for real collaboration —
no follower counts, no engagement farming, just creative output.
Available on iOS and Android.
```

### CTA buttons

```
[Join the Waitlist]   [Download on the App Store]   [Get it on Google Play]
```

App Store / Play Store button URLs are driven by env vars:

```
NEXT_PUBLIC_APP_STORE_URL=<IOS_URL>
NEXT_PUBLIC_PLAY_STORE_URL=<ANDROID_URL>
```

Buttons render as `<a>` tags (no client JS required). `noopener noreferrer` on external links.

### Value proposition grid (3 items, neutral placeholders)

| Icon | Heading | Body |
|---|---|---|
| `[ICON_1]` | Real Collaboration, Not Content | `<BRAND_NAME>` is built for artists who want creative partners, not more followers. |
| `[ICON_2]` | AI-Powered Matching | Our matching engine reads your portfolio and creative DNA to surface the right co-founders. |
| `[ICON_3]` | Safe & IP-Protected | Built-in project workspaces, IP-safe audit logs, and mutual-consent AI tools. |

### Anti-pattern framing (pending brand voice)

```
We don't show you ads. We don't measure your time-on-app.
We optimize for one thing: real creative output.
```

---

## 5. Cookie Banner

### Posture (locked by master §0)

Simple "Accept All" banner. EU/UK dropped from launch geos (US/CA/AU/NZ/IN). Granular opt-in/out UI is **not** required and **not** built for v1.

### Cookie Categories

Even though the banner is "Accept All", the categories are documented for legal accuracy and future GDPR preparation:

| Category | Cookies | Always Active? |
|---|---|---|
| **Necessary** | Session cookie (if any SSR fallback), CSRF token, cookie-consent record | Yes — cannot be declined |
| **Analytics** | PostHog `ph_` cookies (session replay, event capture, feature flags) | Accepted via banner |
| **Functional** | Waitlist form state (localStorage), preferred language (none at launch — i18n deferred) | Accepted via banner |
| **Marketing** | Reserved for future ad retargeting (not used at launch) | Accepted via banner |

### Consent Storage

1. On "Accept All" click: write `{ consentVersion: "1", categories: ["necessary","analytics","functional","marketing"], acceptedAt: ISO8601 }` to `localStorage` key `cookie_consent`.
2. Optionally POST `{ consentRecord }` to `POST /api/cookie-consent` for server-side audit trail. This endpoint is a thin route handler that appends to an audit log (not user-linked at this stage — anonymous session).
3. PostHog is initialized **after** consent is recorded (or on page load if consent already exists in localStorage).
4. Banner is hidden once consent exists in localStorage (checked on mount client-side — no flash because banner is rendered server-side with `hidden` attribute if a cookie `consent_given=1` is set by the route handler).

### Banner Component

```tsx
// apps/marketing-web/components/CookieBanner.tsx
'use client'
export function CookieBanner() {
  // reads localStorage on mount; hides if already consented
  // "Accept All" button: writes localStorage, posts to /api/cookie-consent, hides banner
  // Links to /legal/cookies
}
```

- No "Reject" or "Manage Preferences" button — per locked posture.
- Rendered in `app/layout.tsx` as a `<Suspense>`-wrapped client component so it does not block static HTML streaming.
- Accessible: `role="dialog"`, `aria-label="Cookie consent"`, focus-trapped while visible, keyboard-dismissible via Accept.

---

## 6. Waitlist Endpoint

### Route: `POST /api/waitlist`

**File**: `apps/marketing-web/app/api/waitlist/route.ts`

```ts
import { z } from 'zod'
import { SESv2Client, CreateContactCommand } from '@aws-sdk/client-sesv2'

const schema = z.object({
  email: z.string().email().max(254),
  source: z.string().max(64).default('homepage'),
  consentAt: z.string().datetime().optional(),  // CASL — Canadian visitors
})

export async function POST(req: Request) {
  const body = await req.json()
  const parsed = schema.safeParse(body)
  if (!parsed.success) return Response.json({ error: 'invalid_input' }, { status: 422 })

  const { email, source, consentAt } = parsed.data
  const ipRaw = req.headers.get('x-forwarded-for') ?? 'unknown'
  const ipHashed = await hashIp(ipRaw)  // SHA-256, one-way

  // 1. Idempotency — check duplicate (via DB or SES list lookup)
  // 2. SES: add contact to list
  const ses = new SESv2Client({ region: process.env.AWS_REGION })
  await ses.send(new CreateContactCommand({
    ContactListName: process.env.WAITLIST_LIST_NAME,
    EmailAddress: email,
    TopicPreferences: [{ TopicName: 'waitlist', SubscriptionStatus: 'OPT_IN' }],
  }))

  // 3. Persist WaitlistEmail row (via internal API call to notification-svc or direct DB)
  // ...

  // 4. Send confirmation email via SES template
  // ...

  return Response.json({ ok: true }, { status: 201 })
}
```

**WaitlistEmail entity** (owned by this spec, persisted in `notification-svc` schema or a standalone table):

```sql
CREATE TABLE waitlist_emails (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       TEXT NOT NULL UNIQUE,
  source      TEXT NOT NULL DEFAULT 'homepage',
  consent_at  TIMESTAMPTZ,            -- CASL consent timestamp
  ip_hashed   TEXT,                   -- SHA-256 of raw IP
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Form component** (`apps/marketing-web/components/WaitlistForm.tsx`):

- `<form>` with email input + CASL consent checkbox (shown only for CA geo-detected visitors via `Intl` or IP header; defaults to shown for all to be safe).
- Submit calls `POST /api/waitlist`, shows inline success/error state.
- No page reload. Client component (`'use client'`).
- Accessible: label + aria-describedby for error messages.

---

## 7. SEO

### Per-Page Metadata

Each page exports a `generateMetadata()` function (App Router convention):

```ts
export const metadata: Metadata = {
  title: 'Page Title | <BRAND_NAME>',
  description: '...',
  alternates: { canonical: 'https://<DOMAIN>/page' },
  openGraph: {
    title: '...',
    description: '...',
    url: 'https://<DOMAIN>/page',
    siteName: '<BRAND_NAME>',
    images: [{ url: '/og/page.png', width: 1200, height: 630 }],
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: '...',
    description: '...',
    images: ['/og/page.png'],
  },
}
```

MDX legal pages derive metadata from frontmatter — no manual export needed.

### Global Metadata Defaults (`app/layout.tsx`)

```ts
export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL!),
  title: { default: '<BRAND_NAME>', template: '%s | <BRAND_NAME>' },
  description: 'AI-powered networking and collaboration for artists and creators.',
  robots: { index: true, follow: true },
}
```

### Robots.txt (`next-sitemap`)

```
User-agent: *
Allow: /
Disallow: /api/

Sitemap: https://<DOMAIN>/sitemap.xml
```

### Canonical URLs

- All pages set `alternates.canonical` explicitly to prevent duplicate indexing from query params.
- `next-sitemap` generates canonical URLs from `siteUrl` env var.

### Structured Data Summary

| Page | Schema |
|---|---|
| All pages | Organization + WebSite (global layout) |
| `/faq` | FAQPage |
| `/blog/[slug]` (future) | Article |

---

## 8. Performance

### Targets

| Metric | Target |
|---|---|
| LCP | < 2.5s on simulated 4G (Lighthouse Mobile) |
| Lighthouse Performance | ≥ 90 |
| Lighthouse Accessibility | ≥ 95 |
| Lighthouse SEO | 100 |
| Lighthouse Best Practices | ≥ 95 |
| FID / INP | < 100ms |
| CLS | < 0.1 |

### Strategies

- **Static export** eliminates TTFB variance — HTML served from CloudFront edge.
- **Font optimization**: `next/font/google` with `display: 'swap'`; subset to Latin. Preloaded. Falls back to system fonts until brand typeface is locked.
- **Image optimization**: All hero and content images pre-optimized via `sharp` at build time. `<Image>` with explicit `width`/`height` to prevent CLS. Hero image: `priority` prop (preloaded).
- **Minimal client JS**: `'use client'` used only for CookieBanner and WaitlistForm. All other components are server components (render to static HTML).
- **Partial Prerendering (PPR)**: Not applicable for full static export. Deferred if a hybrid deploy model is adopted later.
- **CSS**: Tailwind CSS with PurgeCSS at build. No runtime CSS-in-JS.
- **Third-party scripts**: PostHog loaded `strategy="lazyOnload"` after cookie consent. No other third-party scripts at launch.
- **Bundle analysis**: `@next/bundle-analyzer` run in CI; alert if client bundle exceeds 50 kB gzipped.
- **Preconnect hints**: `<link rel="preconnect">` for PostHog ingest domain, AWS S3/CloudFront.

---

## 9. CMS Path

### v1 — MDX in Repository

- **Location**: `apps/marketing-web/content/`
- **Structure**:

  ```
  content/
    legal/
      tos.mdx
      privacy.mdx
      community-guidelines.mdx
      dmca.mdx
      cookies.mdx
    blog/
      .gitkeep          ← empty until blog ships
    faq/
      index.mdx         ← Q&A pairs as frontmatter array
  ```

- Legal pages: updated by editing MDX files, committing, triggering CI/CD deploy.
- FAQ: frontmatter-driven array of `{ question, answer }` objects — no database needed.
- Blog: route reserved; `content/blog/` populated when blog ships (v1.1).

### v1.1+ — Headless CMS (Deferred)

- **Sanity** (preferred) or Contentful evaluated at v1.1 when editorial velocity requires it.
- Migration path: MDX files → import script → Sanity studio. Next.js page code remains the same; data source abstracted behind a `getContent(slug)` adapter.
- Decision owner: Phase 5 design pass.

---

## 10. Implementation Tasks

| ID | Title | Outcome | Est. Hours | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-01 | Scaffold `marketing-web` Next.js 15 app | Repo monorepo package `apps/marketing-web` with App Router, TypeScript strict, Tailwind, `next.config.ts` with static export + MDX | 4h | T-02, T-03, T-04 | 002 Shared Platform (design tokens package) |
| T-02 | Configure `@next/mdx` + content directory | MDX pipeline wired; `apps/marketing-web/content/` structure created; `<MDXLayout>` component | 2h | T-07, T-08 | T-01 |
| T-03 | Implement global layout + nav + footer | `app/layout.tsx` with global metadata, JSON-LD (Organization + WebSite), nav links, footer (legal links + app badges), CookieBanner slot | 4h | T-05, T-06 | T-01 |
| T-04 | Set up `next-sitemap` + `robots.txt` | `postbuild` script generates `sitemap.xml` + `robots.txt`; tested against known page list | 2h | — | T-01 |
| T-05 | Build homepage (`/`) | Hero, value prop grid, "how it works" 3-step, testimonials placeholder, FAQ teaser, app store badges, WaitlistForm integration | 8h | — | T-03, T-10 |
| T-06 | Build `/how-it-works` page | 3-step detailed breakdown, animated diagram placeholder (CSS, no JS library) | 3h | — | T-03 |
| T-07 | Build `/faq` page + FAQPage JSON-LD | MDX-driven Q&A, client-side text filter (`'use client'` island), FAQPage schema | 3h | — | T-02, T-03 |
| T-08 | Build `/about` page | Mission statement, team placeholder grid, values section | 2h | — | T-02, T-03 |
| T-09 | Write all 5 legal MDX documents | `tos.mdx`, `privacy.mdx`, `community-guidelines.mdx`, `dmca.mdx`, `cookies.mdx` — placeholder legal copy (reviewed by legal counsel before launch) | 6h | — | T-02 |
| T-10 | Implement `WaitlistForm` component + `POST /api/waitlist` | Form component (email + CASL checkbox), route handler (zod validation → SES → DB row → confirmation email), duplicate handling | 6h | T-05 | T-01, SES list configured |
| T-11 | Implement `CookieBanner` component + `POST /api/cookie-consent` | Client component, localStorage consent write, PostHog lazy-init, audit log endpoint | 3h | T-03 | T-01 |
| T-12 | OG image generation script | `scripts/generate-og.ts` using `@vercel/og` `ImageResponse`; writes PNGs to `public/og/`; runs as `prebuild` step | 3h | T-05, T-06, T-07, T-08 | T-01 |
| T-13 | Reserve `/blog` route + stub | `/blog/page.tsx` "Coming soon" stub; `/blog/[slug]/page.tsx` returning 404 shell; MDX reader wired but no content | 1h | — | T-02 |
| T-14 | Per-page metadata + canonical tags | Every page exports `generateMetadata()`; OG + Twitter cards; canonical URLs | 3h | T-05…T-09, T-13 | T-12 |
| T-15 | CloudFront + S3 deploy pipeline | GitHub Actions workflow: `npm run build` → `aws s3 sync out/ s3://$BUCKET` → CloudFront invalidation. Cache-control response headers policy via CDK/Terraform | 5h | — | T-01, AWS infra ready |
| T-16 | Accessibility audit | Run `axe-core` in Playwright test suite against all pages; fix violations until Lighthouse A11y ≥ 95 | 4h | T-05…T-09, T-13 | T-14 |
| T-17 | Lighthouse CI integration | `lighthouse-ci` in GitHub Actions; asserts Performance ≥90, A11y ≥95, SEO 100; fails PR if below threshold | 2h | T-16 | T-15 |
| T-18 | `WaitlistEmail` DB migration | SQL migration file for `waitlist_emails` table in appropriate service schema | 1h | T-10 | DB schema tooling ready |
| T-19 | E2E smoke tests (Playwright) | Waitlist form submit, cookie banner accept, all pages return 200, sitemap accessible | 3h | T-05…T-13 | T-15 |

**Total estimated**: ~65 hours.

**Critical path**: T-01 → T-03 → T-05 → T-14 → T-16 → T-17.

---

## 11. Acceptance Criteria

### AC-1 — All Pages Render and Return 200

- [ ] Static build produces HTML for every route in §3.
- [ ] `/blog` returns 200 with "Coming soon" stub; `/blog/[slug]` returns 404 shell (not a build error).
- [ ] Verified via `curl` against CloudFront distribution after deploy.

### AC-2 — Lighthouse Scores (Mobile Simulation, Throttled 4G)

Run against CloudFront URL (not localhost):

- [ ] Performance ≥ 90
- [ ] Accessibility ≥ 95
- [ ] SEO = 100
- [ ] Best Practices ≥ 95
- [ ] LCP < 2.5s
- [ ] CLS < 0.1

Verified via `lighthouse-ci` in GitHub Actions (fails build if below threshold).

### AC-3 — axe-core Zero Critical/Serious Violations

- [ ] Playwright + `@axe-core/playwright` run on all routes.
- [ ] Zero `critical` or `serious` violations.
- [ ] `moderate` violations documented in `ACCESSIBILITY.md` with timeline to fix.

### AC-4 — Sitemap and Robots

- [ ] `https://<DOMAIN>/sitemap.xml` returns valid XML with all routes in §3 (excluding `/api/*` and `/blog/[slug]` until blog ships).
- [ ] `https://<DOMAIN>/robots.txt` present; `Disallow: /api/` present; Sitemap URL present.
- [ ] Validate with Google Search Console URL Inspection after deploy.

### AC-5 — OG Tags and Structured Data

- [ ] All pages pass [opengraph.xyz](https://www.opengraph.xyz) preview test.
- [ ] All pages pass [Google Rich Results Test](https://search.google.com/test/rich-results) for applicable schemas.
- [ ] `Organization` + `WebSite` JSON-LD present on every page (via layout).
- [ ] `FAQPage` JSON-LD present on `/faq` only.

### AC-6 — Waitlist Form

- [ ] Valid email submission → 201 response → success confirmation shown inline.
- [ ] Duplicate email → 409 response → friendly "already on the list" message shown.
- [ ] Invalid email → 422 response → inline validation error shown.
- [ ] SES contact list contains the submitted email after successful submission.
- [ ] `waitlist_emails` DB row created with `email`, `source`, `ip_hashed`, `created_at`.
- [ ] CASL consent checkbox shown and `consent_at` populated when checked.

### AC-7 — Cookie Banner

- [ ] Banner visible on first visit (no prior localStorage consent).
- [ ] "Accept All" click: banner disappears, `localStorage.cookie_consent` set, PostHog initialized.
- [ ] On return visit (localStorage consent present): banner not shown, PostHog initializes on load.
- [ ] Banner is keyboard-accessible (Tab to button, Enter to accept).
- [ ] `role="dialog"` and `aria-label="Cookie consent"` present.

### AC-8 — Legal Pages

- [ ] All 5 legal MDX documents render at their routes.
- [ ] `lastUpdated` frontmatter displays correctly.
- [ ] All legal links in footer resolve without 404.

### AC-9 — CloudFront Cache-Control

- [ ] `/_next/static/*` responses include `Cache-Control: public, max-age=31536000, immutable`.
- [ ] `/` and `.html` responses include `s-maxage=86400`.
- [ ] Verified via `curl -I https://<DOMAIN>/` and inspecting `Cache-Control` header.

### AC-10 — Security Headers

- [ ] All HTML responses include `X-Frame-Options: DENY`.
- [ ] All HTML responses include `X-Content-Type-Options: nosniff`.
- [ ] All HTML responses include `Referrer-Policy: strict-origin-when-cross-origin`.
- [ ] Verify via [securityheaders.com](https://securityheaders.com).

### AC-11 — Static Export Purity

- [ ] No server-rendered pages (all `.html` files present in `out/` after build).
- [ ] No `getServerSideProps` usage (App Router only, no Pages Router).
- [ ] Only `'use client'` components are `CookieBanner`, `WaitlistForm`, and the FAQ search filter.
- [ ] Client JS bundle for non-interactive pages: ≤ 50 kB gzipped (verified via `@next/bundle-analyzer`).

### AC-12 — App Store Badge Links

- [ ] iOS badge links to `NEXT_PUBLIC_APP_STORE_URL` (env var, not hardcoded).
- [ ] Android badge links to `NEXT_PUBLIC_PLAY_STORE_URL` (env var, not hardcoded).
- [ ] Both badges render `alt` text for screen readers.
- [ ] Links open in new tab with `rel="noopener noreferrer"`.
- [ ] If env vars are empty (pre-launch), badges are hidden (conditional render).

---

## 12. Open Risks

| Risk ID | Description | Severity | Mitigation |
|---|---|---|---|
| R-01 | **Brand voice and copy are pending Phase 5 ui-ux-pro-max design pass.** All hero, value prop, and about copy ships with `<BRAND_NAME>` tokens and placeholder text. Cannot fully A/B test or SEO-optimize until copy is locked. | High | Plan build pipeline to swap tokens via env vars or a single `brand.config.ts` constants file. Copy review is a hard gate before go-live. |
| R-02 | **User-facing brand name is TBD** (codename `Colab`). Domain, OG image text, sitemap URL, App Store listing name all depend on brand lock. | High | All env vars driven by `NEXT_PUBLIC_BRAND_NAME`, `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_DOMAIN`. Deploy pipeline substitutes at build time. |
| R-03 | **DMCA agent registration is deferred.** The `/legal/dmca` page must not claim US DMCA safe-harbor explicitly. Legal copy must be reviewed before launch. | High | Legal counsel to review DMCA page content. Placeholder copy explicitly omits safe-harbor claim. |
| R-04 | **Waitlist `POST /api/waitlist` is not statically exportable.** Requires a runtime compute layer (Lambda@Edge, Fargate, or gateway proxy). Infrastructure decision deferred. | Medium | Route handler contract is fixed. Infrastructure team selects runtime. Fallback: third-party form service (Formspree / Basin) as interim. |
| R-05 | **Blog route deferred to v1.1.** Stub at `/blog` may attract crawler indexing of thin content. | Low | `<meta name="robots" content="noindex">` on the stub page until blog ships. |
| R-06 | **App Store / Play Store URLs not available until P18 (store submissions).** Badge links will be broken until then. | Low | Conditional render: badges hidden if env vars are empty. Set env vars to a landing page placeholder if stores go live before marketing site relaunch. |
| R-07 | **PostHog cookie consent interlock.** If the cookie banner fails to load (JS error, ad blocker), PostHog must not initialize. | Medium | PostHog initialization is deferred to a `useEffect` callback that only runs if consent exists in localStorage. Default state: no PostHog. |
| R-08 | **CASL compliance for Canadian waitlist signups.** Single opt-in is sufficient but consent timestamp must be stored. If email marketing list is used commercially, a CASL-compliant unsubscribe mechanism is required in all emails. | Medium | `consent_at` column in `waitlist_emails`. SES confirmation email includes unsubscribe link. Legal review before first marketing email send. |
| R-09 | **India DPDP — waitlist email data.** If Indian users sign up for the waitlist, their data is stored in us-east-1. Full India data localization requirements are Phase 5 deferred. | Low | Noted as open; data processor agreements cover for now. Revisit at Phase 5. |
| R-10 | **Design token package (002 Shared Platform) may not be ready at P16.** Marketing site could be blocked. | Medium | Use a local `tokens.css` stub with CSS variables until 002 ships. Merge token package at design pass. |

---

## Appendix A — File and Directory Map

```
apps/marketing-web/
  app/
    layout.tsx                    ← global layout, JSON-LD (Org + WebSite), CookieBanner slot
    page.tsx                      ← homepage (/)
    how-it-works/
      page.tsx
    faq/
      page.tsx
    about/
      page.tsx
    legal/
      tos/page.tsx
      privacy/page.tsx
      community-guidelines/page.tsx
      dmca/page.tsx
      cookies/page.tsx
    blog/
      page.tsx                    ← "Coming soon" stub, noindex
      [slug]/
        page.tsx                  ← 404 shell until blog ships
    api/
      waitlist/
        route.ts
      cookie-consent/
        route.ts
  components/
    CookieBanner.tsx              ← 'use client'
    WaitlistForm.tsx              ← 'use client'
    MDXLayout.tsx
    AppStoreBadges.tsx
    JsonLd.tsx                    ← thin wrapper for <Script type="application/ld+json">
  content/
    legal/
      tos.mdx
      privacy.mdx
      community-guidelines.mdx
      dmca.mdx
      cookies.mdx
    blog/
      .gitkeep
    faq/
      index.mdx
  public/
    og/                           ← pre-generated OG images (built by scripts/generate-og.ts)
    images/
    fonts/
  scripts/
    generate-og.ts
  next.config.ts
  next-sitemap.config.js
  tailwind.config.ts
  tsconfig.json
  package.json
```

---

## Appendix B — Environment Variables

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_SITE_URL` | Yes | Full URL of the site (e.g. `https://example.com`) |
| `NEXT_PUBLIC_BRAND_NAME` | Yes | Brand name token (e.g. `<BRAND_NAME>` until locked) |
| `NEXT_PUBLIC_APP_STORE_URL` | No | iOS App Store URL (badges hidden if empty) |
| `NEXT_PUBLIC_PLAY_STORE_URL` | No | Google Play URL (badges hidden if empty) |
| `NEXT_PUBLIC_POSTHOG_KEY` | Yes | PostHog project API key |
| `NEXT_PUBLIC_POSTHOG_HOST` | Yes | PostHog ingest host |
| `WAITLIST_LIST_NAME` | Yes | SES contact list name for waitlist |
| `AWS_REGION` | Yes | AWS region for SES client |
| `DATABASE_URL` | Yes | Postgres connection string (for waitlist row write) |

---

*End of plan — 017 Marketing Site.*
