# 017 — Marketing Site

**Phase**: P16.
**App**: `marketing-web` (Next.js, static-export-friendly).
**Mission**: Public landing page for SEO + signup-intent capture. App Store / Play Store badges. Privacy / ToS / Community Guidelines / DMCA / Cookies pages.

## In scope

- Landing page: hero, value props (anti-brain-rot framing), 3-step "how it works", testimonials placeholder, FAQ teaser, footer with all legal links.
- App Store + Play Store deep-link buttons (resolved by `BRAND_NAME` constant + per-env URLs).
- Legal pages: Terms of Service, Privacy Policy, Community Guidelines, DMCA notice, Cookie Policy.
- Cookie banner: "Accept All" simple banner (per R22 + R22b — only acceptable because EU/UK dropped).
- Email capture for waitlist (Mailchimp / SES list).
- SEO: per-page metadata, OG tags, JSON-LD schema, sitemap.xml, robots.txt.

## Dependencies

- **Hard**: 002 Shared Platform (Next.js base + design tokens).
- **Soft**: 014 Notifications (email capture posts to a list).

## Owned entities (small)

- `WaitlistEmail`: id, email, source (page), created_at, ip (hashed).

## API surface

- `POST /api/waitlist` (Next.js route handler) body `{email, source}`

## Acceptance criteria

- LCP <2.5s on 4G.
- Lighthouse: Performance ≥90, Accessibility ≥95, SEO 100.
- Sitemap auto-generated from MDX content.
- All legal pages render from `apps/marketing/content/*.mdx`.
- Email signup posts and shows confirmation.

## NFRs

- Static + CloudFront cached.
- No client-side JS for static content paths beyond what Next ships.

## Open

- Final brand voice + design — Phase 5 design pass (ui-ux-pro-max skill).
- Whether to ship blog at launch — Phase 5; recommend "no" until v1.1.
