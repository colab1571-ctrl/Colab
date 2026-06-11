# DEPLOY-RESUME.md — Colab PaaS Deploy session

> Last updated: 2026-06-11. Stage 3 PaaS deploy **COMPLETE** for the first slice (gateway + auth + profile + marketing-web + consumer-web + admin-web). Full backend ↔ frontend chain verified live.

## tl;dr

| Layer | Status | URL |
|---|---|---|
| **Backend (Render)** — gateway, auth, profile | ✅ live, /healthz 200, signup 201 | https://colab-gateway-ogv8.onrender.com |
| **Database (Supabase)** — Postgres 17 + auth/profile migrations | ✅ ACTIVE_HEALTHY, schema applied | pooler `aws-1-us-west-2.pooler.supabase.com:5432` |
| **Cache (Upstash)** — Redis | ✅ live | fitting-eagle-77213.upstash.io:6379 |
| **Queue (CloudAMQP)** — RabbitMQ | ✅ live | beaver.rmq.cloudamqp.com |
| **Frontend (Vercel)** — marketing-web | ✅ 200 | https://marketing-k871hpov1-amay-singhs-projects-253cec62.vercel.app |
| **Frontend (Vercel)** — consumer-web | ✅ 200 | https://consumer-96n0kvvbg-amay-singhs-projects-253cec62.vercel.app |
| **Frontend (Vercel)** — admin-web | ✅ 307→/dashboard | https://admin-p9nvvjd5s-amay-singhs-projects-253cec62.vercel.app |

End-to-end signup verified: HTTP 201, RS256 JWT, user_id `57d95747-7379-4bdb-8e56-9110045734ff` written to Supabase via `Vercel client → Render gateway → Render auth → Supabase` chain in 3.6s. (Cold start: 15s gateway, 45s auth.)

## All 14 steps

| # | Step | State |
|---|---|---|
| 1 | Pick deploy target (Render + Vercel + Supabase + Upstash + CloudAMQP) | ✅ |
| 2 | Create Render account | ✅ workspace `tea-d3fc2hili9vc73ee9qtg` |
| 3 | Create Supabase project + PAT | ✅ `colab-dev` (`obtqouqjqedfosgumkxu`) |
| 4 | Enable Postgres extensions | ✅ postgis 3.3.7, vector 0.8.0, pg_trgm 1.6, uuid-ossp 1.1 |
| 5 | Create Upstash Redis | ✅ rediss://fitting-eagle-77213.upstash.io:6379 |
| 6 | Create CloudAMQP RabbitMQ | ✅ amqps://beaver.rmq.cloudamqp.com |
| 7 | Write render.yaml Blueprint | ✅ commit `2b039ad` |
| 8 | Commit + push render.yaml | ✅ |
| 9 | Create Render Blueprint from repo | ✅ via Playwright-driven Chrome (Blueprint id `exs-d8l2bjv7f7vs73fidmcg`) |
| 10 | Set per-service env vars | ✅ via Render MCP |
| 11 | First deploy + verify /healthz | ✅ all 3 services live (deploy ~3.5 min) |
| 12 | Run Alembic migrations | ✅ auth 0001 + profile 0001→0006 |
| 13 | Vercel link 3 web apps | ✅ deployed via Vercel CLI from monorepo root with rootDirectory project setting |
| 14 | Smoke test live URLs | ✅ 6/6 PASS via demo_signup.sh; full e2e signup 201 in 3.6s |

## Render service IDs

| Service | ID | URL |
|---|---|---|
| colab-gateway | `srv-d8l2c33tqb8s73anh0t0` | https://colab-gateway-ogv8.onrender.com |
| colab-auth | `srv-d8l2c33tqb8s73anh0u0` | https://colab-auth-m6yp.onrender.com |
| colab-profile | `srv-d8l2c33tqb8s73anh0tg` | https://colab-profile.onrender.com |

Workspace `tea-d3fc2hili9vc73ee9qtg`. autoDeploy: no (toggle via dashboard if desired).

## Vercel project IDs

Team `team_Zzzo09YOx9eZYDx1giSwy0sy` (`amay-singhs-projects-253cec62`).

| App | Project ID | URL |
|---|---|---|
| marketing-web | `prj_<marketing>` | marketing-k871hpov1-amay-singhs-projects-253cec62.vercel.app |
| consumer-web | `prj_f9xRZhIIXi1ImO419aBDB08SARfG` | consumer-96n0kvvbg-amay-singhs-projects-253cec62.vercel.app |
| admin-web | `prj_SAnvzMI9O4r3kSbPhQ6dc5EVLwIX` | admin-p9nvvjd5s-amay-singhs-projects-253cec62.vercel.app |

Each project has:
- `NEXT_PUBLIC_API_URL=https://colab-gateway-ogv8.onrender.com` (production + preview + development)
- `rootDirectory=apps/<app>` (lets monorepo lockfile and workspace packages resolve)
- `buildCommand` overridden to install workspace from root then build the filter
- Deployment Protection (SSO) **disabled** — apps are publicly accessible

Deploy command pattern: from monorepo root, swap `.vercel/project.json` to point at the target project, then `vercel deploy --prod --yes --token <T> --scope amay-singhs-projects-253cec62`.

## Frontend bugs fixed in this deploy

Six pre-existing app code bugs surfaced only when running a real Vercel build (not local pnpm dev). All fixed in 3 atomic commits on `feat/stage3-paas-deploy`:

- `15112d2 fix(stage3-frontend): unblock marketing-web Vercel build`
  - Added `@mdx-js/loader` dep (transitively pulled in local but not by `pnpm install --frozen-lockfile`)
  - Replaced unclosed `<BRAND_NAME>` placeholders in 5 legal MDX files with locked-in brand `Colab`
  - Moved `FaqItem` type + `faqItems` const out of page.tsx (Next 15 Page modules restrict exports)
  - Deleted v1.1 placeholder `blog/[slug]/page.tsx` (empty generateStaticParams + output:export = error)
  - Removed `output:'export'` (was for S3+CloudFront plan; pivoted to Vercel SSR)
  - Disabled `postbuild: next-sitemap` (broken on Node 23/pnpm v9)
- `3d1bbf2 fix(stage3-frontend): unblock consumer-web Vercel build`
  - Added `./theme.css` export to `@colab/ui` exports map so CSS `@import "@colab/ui/theme.css"` resolves
  - Removed orphan side-effect TSX import from consumer-web layout
  - Typed `withAuth` HOC `redirectTo` as `Route` (consumer-web has `experimental.typedRoutes`)
- `9d22771 fix(stage3-frontend): unblock admin-web Vercel build`
  - Removed unsupported `firewall` block from `apps/admin-web/vercel.json` (CLI 48.1.6 rejects)
  - Updated stale `colab-gateway-prod.fly.dev` rewrite destination to live Render URL
  - Updated 3 dynamic-route pages to Next 15's async `params: Promise<...>` shape

## Operational gotchas

- **Supabase pooler host is `aws-1-us-west-2`** (not `aws-0`) — earlier notes had wrong host. DATABASE_URL must use the **session pooler** (port 5432), not transaction pooler (6543), because services rely on prepared statements which transaction pooler doesn't support.
- **Render free-tier services spin down after ~15 min idle.** Cold start = 15s gateway, 45s auth. /healthz wakes them.
- **Vercel "Deployment Protection"** is on by default for personal accounts. Disable via PATCH `/v9/projects/{id}` with `{"ssoProtection":null,"passwordProtection":null}` for public access.
- **Git push hits SIGBUS on macOS** with this repo. Workaround: `git gc; git repack -ad --window=10 --depth=10` then retry. Per RESUME.md, also caused by Spotlight/Windsurf file watch.

## Future improvements (not blocking)

- Wire Vercel custom domains (`colabclub.net`, `app.colabclub.net`, `admin.colabclub.net`)
- Re-enable `firewall` block on admin-web via Vercel dashboard (CLI doesn't accept it but dashboard does)
- Re-enable `postbuild: next-sitemap` once `next-sitemap >= 4.3` ships a Node 23 fix
- Move from `--access-token <flag>` to `.env`-based Supabase MCP config for cleaner setup
- Investigate and fix Supabase + Playwright MCP "stuck connecting" state (packages cached but Claude Code client never finishes init)

## MCP / tooling state

| MCP | Status |
|---|---|
| Render | ✅ Connected, workspace `tea-d3fc2hili9vc73ee9qtg` |
| Vercel | ✅ Connected (OAuth completed) |
| Supabase | ⚠️ Server boots fine; Claude Code client never registers tools. Workaround: direct Mgmt API with PAT |
| Playwright | ⚠️ Same. Workaround: helper scripts at `~/.colab-playwright/{launch,step,wait_login}.mjs` drive Chrome via npm package directly |
| Google Drive | 🔐 Not authenticated (not deploy-relevant) |

A full Claude Code restart should fix Supabase + Playwright MCPs since the npx packages are now cached at `~/.npm/_npx/`.
