# 013 — Billing + Subscriptions + Credits + Entitlements

**Phase**: P12.
**Services**: `billing-svc`.
**Mission**: Free + Premium + Premium Pro subscriptions across iOS, Android, and Web. Credit wallet for AI consumption. Entitlement evaluation API for every other service. Dunning. Refunds. Tax.

## In scope (master Journey E FR-E-1 through FR-E-8)

- Tier model: Free / Premium / Premium Pro. Monthly + annual SKUs at launch. Values admin-configurable.
- Entitlement axes (R19): `invites_per_week`, `ai_credits_per_month`, `ads_shown`, `chat_export`, `hide_from_non_premium`, `picked_for_you_priority`, `mockup_fidelity`, `portfolio_pdf_export`, `visibility_boost`, `support_priority`, `see_who_saved_you`.
- Mobile IAP via RevenueCat (Apple IAP + Play Billing). Web via Stripe Checkout.
- Cross-platform entitlement parity: RevenueCat as the source of truth for mobile; Stripe-as-Backend integration syncs web subs to the same RevenueCat user record.
- Credit Wallet: balance, transactions, top-up via Stripe (web) or in-app one-time Apple/Play products.
- Dunning state machine: Day 0/3/7 retries + email; Day 10 cancel; Day 30 grace-period reactivation.
- Refund: 14-day no-questions full refund; prorated thereafter (annual only); store IAP routes per Apple/Google policy.
- Stripe Tax for web; store-handled for mobile. India GST handled via Stripe Tax + reseller registration path.
- Webhooks: Stripe + RevenueCat → entitlement updates + credit adjustments + audit log.

## Dependencies

- **Hard**: 002, 003.
- **Soft**: 005 (caps + visibility), 006 (invite quota), 007 (chat-export entitlement), 009 (export), 012 (credit metering), 004 (premium visibility), 016 (admin tier-config), 008 (subscription pause on permanent ban).

## Owned entities

- `Customer`: user_id, stripe_customer_id (nullable), revenuecat_user_id (= user_id), preferred_currency, country.
- `Subscription`: user_id, source (stripe|revenuecat), tier (free|premium|pro), status (active|trialing|past_due|paused|canceled|expired), current_period_end, store_subscription_id, started_at, canceled_at.
- `EntitlementSnapshot`: user_id, axis_key, value, source (default|subscription|grant|promo), expires_at (nullable), updated_at. (Always read this table — never re-derive from Subscription on hot paths.)
- `CreditWallet`: user_id, balance, updated_at.
- `CreditTransaction`: id, user_id, delta, reason (purchase|admin_grant|refund|consume), reference (stripe_charge_id|revenuecat_event_id|ai_interaction_id), created_at.
- `Invoice`: stripe-mirrored.
- `RefundRequest`: id, user_id, subscription_id|transaction_id, requested_at, reason, status, decided_at, decided_by.

## API surface

- `GET /billing/entitlements` → current axis values for the calling user
- `GET /billing/subscriptions` → list
- `POST /billing/checkout/web` body `{price_id, return_url}` → Stripe Checkout session URL
- `GET /billing/credits/balance`, `POST /billing/credits/purchase/web` body `{price_id}` → checkout
- `POST /billing/cancel/web`
- `POST /billing/refund-request` body `{subscription_id|transaction_id, reason}`
- `POST /webhooks/stripe` (signed)
- `POST /webhooks/revenuecat` (signed)

### Queue events

- `entitlement.changed` (broadcast — every service that caches entitlements should subscribe and invalidate)
- `credits.consumed`, `credits.purchased`, `credits.granted`
- `subscription.activated`, `subscription.canceled`, `subscription.past_due`
- `refund.granted`

## Acceptance criteria

- New user starts on Free with default entitlements baked into the seed.
- Mobile Premium purchase via App Store → RevenueCat webhook → entitlement table updates → user can send unlimited invites + use AI commands.
- Web Premium purchase via Stripe → mirrored via RevenueCat Stripe integration → same entitlements.
- Credit purchase increments wallet; AI command in §012 decrements.
- Dunning: Day 0 failed → retry email + retry charge; subsequent retries on Day 3/7; cancel Day 10; reactivate within 30d.
- Refund request flow: 14d window auto-approves; later routed to support.

## NFRs

- Entitlement read P95 <50ms (Redis-cached, broadcast invalidate).
- Webhook handlers idempotent with idempotency-key.

## Open

- India GST: who handles remit (Stripe Tax reseller registration vs MoR Paddle as fallback) — Phase 5 detail.
- Sales-tax exemption certificates for non-profits — out of scope this milestone unless flagged.
