# Vercel Deploy Guide

Three web apps: **marketing-web**, **consumer-web**, **admin-web**.

## Prerequisites

```bash
npm i -g vercel          # or: brew install vercel-cli
vercel login             # sign in with GitHub (Hobby tier is free)
```

## 1. Link each app to Vercel

Run from the **monorepo root**:

```bash
cd apps/marketing-web && vercel link && cd ../..
cd apps/consumer-web  && vercel link && cd ../..
cd apps/admin-web     && vercel link && cd ../..
```

Follow the interactive prompts:
- **Set up and deploy?** → No (link only for now)
- **Which scope?** → your personal or team scope
- **Link to existing project?** → No → project name: `colab-marketing`, `colab-consumer`, `colab-admin`

## 2. Set environment variables

### marketing-web
```bash
vercel env add NEXT_PUBLIC_API_URL production --cwd apps/marketing-web
# value: https://api.colabclub.net  (or https://colab-gateway-prod.fly.dev before custom domain)
vercel env add NEXT_PUBLIC_POSTHOG_KEY production --cwd apps/marketing-web
vercel env add SENTRY_DSN production --cwd apps/marketing-web
```

### consumer-web
```bash
vercel env add NEXT_PUBLIC_API_URL production --cwd apps/consumer-web
# value: https://api.colabclub.net
vercel env add NEXT_PUBLIC_POSTHOG_KEY production --cwd apps/consumer-web
vercel env add SENTRY_DSN production --cwd apps/consumer-web
vercel env add NEXT_PUBLIC_MAPBOX_TOKEN production --cwd apps/consumer-web
vercel env add NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY production --cwd apps/consumer-web
```

### admin-web
```bash
vercel env add NEXT_PUBLIC_API_URL production --cwd apps/admin-web
# value: https://api.colabclub.net
vercel env add SENTRY_DSN production --cwd apps/admin-web
```

> **Bulk import:** You can also use `vercel env pull .env.local` to pull existing vars and
> `vercel env add < envfile` for batch import.

## 3. Deploy to production

```bash
vercel deploy --prod --cwd apps/marketing-web
vercel deploy --prod --cwd apps/consumer-web
vercel deploy --prod --cwd apps/admin-web
```

Each command outputs a production URL like `https://colab-marketing.vercel.app`.

## 4. Custom domains (colabclub.net)

```bash
vercel domains add colabclub.net          --cwd apps/marketing-web
vercel domains add app.colabclub.net      --cwd apps/consumer-web
vercel domains add admin.colabclub.net    --cwd apps/admin-web
```

Add corresponding DNS records at your registrar:
```
colabclub.net        A      76.76.21.21
app.colabclub.net    CNAME  cname.vercel-dns.com
admin.colabclub.net  CNAME  cname.vercel-dns.com
```

## 5. Admin-web IP allowlist

`apps/admin-web/vercel.json` includes a Vercel Firewall block rule. You must:
1. Go to Vercel dashboard → `colab-admin` project → **Security** → **Firewall**.
2. Edit the "Block non-corporate IPs" rule — replace `0.0.0.0/0` with your actual office/VPN CIDRs.
3. Save. Vercel applies the rule globally within ~30s.

> **Note:** Vercel Firewall IP rules require the **Pro** plan. On the free Hobby tier, protect admin-web using NextAuth + role-based middleware instead (already scaffolded in `apps/admin-web/middleware.ts`).

## 6. Verify deployments

```bash
curl https://colabclub.net               # → 200 marketing landing
curl https://app.colabclub.net           # → 200 consumer app shell
curl https://admin.colabclub.net         # → 302 → login (if middleware active)
```
