# 013 — Billing + Subscriptions + Credits + Entitlements — PLAN

> Phase: **P12** (master roadmap). Service: `billing-svc`. Status: **READY-TO-BUILD** after Phase 5 detailing. Sibling specs referenced: `000-master` (locked decisions), `013-billing/spec.md` (this feature), `016-admin-analytics` (admin tier-config surface), `012-ai-orchestrator` (credit consumer), `008-moderation` (subscription-pause on ban).

---

## 1. Mission recap

Build the **monetization spine** of Colab. Three jobs, in priority order:

1. **Charge users correctly** across iOS, Android, and Web — Apple IAP + Google Play Billing routed through **RevenueCat**; web checkout + partner/credit one-off charges via **Stripe**. Tax via **Stripe Tax** (web) and store-handled (mobile). India GST is the open commercial question.
2. **Grant entitlements deterministically** — every other service in the platform asks `billing-svc` "what can this user do right now?" and gets a fast, cached answer. Eleven entitlement axes (per FR-E-2), each admin-configurable per tier in §016.
3. **Meter AI consumption** via a credit wallet — `/mockup-*` commands in §012 *reserve* credits before invoking Replicate, *commit* on success, *refund* on failure. Top-up via Stripe (web) or one-shot Apple/Play products (mobile).

Three tiers at launch: **Free / Premium / Premium Pro**, monthly + annual SKUs. Prices admin-configurable; never hard-coded in code.

Money-critical invariants:

- **No double-charge.** Every webhook handler is idempotent on the provider event id.
- **No silent entitlement drift.** Every state change writes `entitlement.changed` to RabbitMQ; subscribers invalidate their caches.
- **No lost credits.** Wallet transactions are append-only; balance is a derived materialization with periodic reconciliation.
- **No refund-after-cancel race.** Refund decision is atomic against subscription state.
- **14-day no-questions refund.** Auto-approved within window; routed to support outside it.
- **Cross-platform parity.** A user with both an iOS sub and a Stripe sub is on the **highest tier** of the two, with the **latest** `current_period_end`.

Out of scope this milestone (locked deferrals from master):

- Journey D ads / coupon UI (schema lives in `coupon-svc` stub; this plan does not consume it).
- EU/UK launch (no VAT MOSS, no SCA-only-EU edge cases beyond what Stripe handles by default).
- Multi-currency at the price-config level beyond the five launch geos' default currencies (USD/CAD/AUD/NZD/INR). Stripe Tax + RevenueCat handle their own rounding.
- B2B invoicing / wire / ACH for enterprise. Card + Apple Pay + Google Pay only.

---

## 2. Research

### 2.1 Stripe API version pinning

- **Pin to a dated API version per deployment.** Choose the latest stable at infra bootstrap (target `2025-10-29` or later, subject to confirmation at P0 close). Pin in two places: (a) `STRIPE_API_VERSION` env var consumed by the Stripe Python SDK constructor; (b) the **Stripe Dashboard webhook endpoint** (webhook deliveries are versioned independently of the SDK and must match).
- **Why pinning matters here:** Stripe changes the shape of `Invoice`, `Subscription`, `Charge` between API versions. An accidental dashboard-driven upgrade can break our webhook handlers silently. CI gate: `billing-svc` startup logs the pinned version + Stripe SDK version; alert if mismatch.
- **Upgrade ritual:** read changelog → bump dev env → run replay suite (Section 14) against a Stripe test-mode shadow → bump staging → bump prod webhook endpoint last (Stripe lets two endpoints coexist on different versions during cutover).
- **Idempotency-Key header on outgoing calls:** required for every `create`-style call. Key format: `{operation}:{user_id}:{intent_id}:{retry_n}` where `intent_id` is a UUID we mint per logical request. TTL of idempotency keys on Stripe's side is 24h; for >24h retries we mint a fresh key and rely on the provider event ledger to dedupe at the webhook step.

### 2.2 Stripe Tax

- **Enable `automatic_tax: { enabled: true }` on every Checkout Session and Subscription create.** Stripe calculates tax at checkout based on the customer's billing address + product tax codes.
- **Tax codes:** assign Stripe tax codes per product. SaaS subscription → `txcd_10103000` (SaaS — General). Credit bundles → consumable digital goods, `txcd_10000000`. Confirm with Stripe Tax team during P0; Phase 5b will lock the exact codes.
- **Customer Tax IDs:** collect via Checkout's built-in `tax_id_collection: { enabled: true }`. India GSTIN, Australia ABN, Canada GST/HST, NZ GST, US states (no national VAT). RevenueCat does not collect tax IDs; that's a store concern on mobile.
- **Origin:** Colab's legal entity is US-domiciled at launch (assumed; legal to confirm). Stripe Tax Origin Address must be set; nexus registrations need to be filed in any US state above its economic-nexus threshold (handled by finance, not engineering — but billing-svc records the address used).
- **India GST:** Stripe Tax does support India, but **only if Colab is registered as a GST taxpayer in India** *or* uses Stripe's reseller-of-record path (limited availability). If neither, fall back to **Paddle MoR** as a regional gateway for India only — schema accommodation: `Subscription.gateway` can be `stripe | revenuecat | paddle_in`. Decision locked at Phase 5b finance review.

### 2.3 Stripe Checkout

- **Mode:** `subscription` for Premium/Pro purchases; `payment` for credit bundle one-offs.
- **Line items:** server constructs from `EntitlementConfig`-linked `STRIPE_PRICE_ID_*`. Never accept client-supplied price IDs.
- **Success/cancel URLs:** signed with a short-lived `checkout_intent_id` so we can correlate to our internal record post-redirect.
- **Customer creation:** call `customer.create` lazily on first checkout, store `stripe_customer_id` on `Customer`. Pass `client_reference_id = user_id`.
- **Promo codes:** Stripe-side coupon support stays disabled this milestone (Journey D deferred). Schema lives in `coupon-svc`; billing-svc reads but does not write.
- **Apple Pay / Google Pay on web:** enabled by default on Stripe Checkout for all five launch regions; no extra config needed.

### 2.4 RevenueCat REST API + webhooks

- **REST v1** is what we use server-to-server: `/v1/subscribers/{app_user_id}` for the subscriber object, `/v1/subscribers/{app_user_id}/entitlements/{ent_id}/promotional` for grants/revokes. **v2** is paginated reporting (revenue, churn) — analytics-svc consumes that, not billing-svc.
- **`app_user_id` == our internal `user_id`.** Set on the client via `Purchases.logIn(user_id)` after auth. RevenueCat treats anonymous purchases as separate users and we **must** call `logIn` before the first purchase or we'll be stuck reconciling later.
- **Webhook events we handle:** `INITIAL_PURCHASE`, `RENEWAL`, `NON_RENEWING_PURCHASE` (credit packs on mobile), `CANCELLATION`, `EXPIRATION`, `BILLING_ISSUE`, `PRODUCT_CHANGE`, `SUBSCRIBER_ALIAS`, `TRANSFER`, `SUBSCRIPTION_PAUSED`.
- **Webhook signature:** `Authorization: <REVENUECAT_WEBHOOK_SECRET>` (RC sends a static bearer; rotate quarterly). Verify with constant-time compare.
- **Event ledger:** persist every raw webhook in `RcEventLedger` (id = RC event id) before processing; gives us replay + idempotency.

### 2.5 RevenueCat Stripe-as-Backend integration

- **Why we use it:** keeps RevenueCat the single source of truth for entitlements regardless of platform. When a web user buys via Stripe, RevenueCat's Stripe integration ingests the subscription as an `app_user_id`-keyed entry, and the *same* webhook pipeline fires.
- **Setup:** in RC dashboard, link the Stripe account; map Stripe Products → RC Offerings → Entitlements. Our `EntitlementConfig` table is the *application-level* mapping from RC entitlements → axis values, NOT the store mapping.
- **Caveat:** RC's Stripe integration requires us to **send the `client_reference_id = user_id`** on the Checkout Session for them to attach. Already in plan. If missing, RC ingests under an orphan id and we have to manually `POST /v1/subscribers/{user_id}/attribution` to fix.
- **Caveat 2:** RC's Stripe integration is **read-mostly** — for refunds we still call Stripe directly. RC observes the resulting `charge.refunded` webhook and propagates.

### 2.6 Idempotency keys on webhooks

- Two layers of idempotency:
  - **Provider event id** (Stripe `event.id`, RevenueCat `event.id`) → unique constraint on `WebhookEventLedger.provider_event_id`. Second delivery of the same event short-circuits at the ledger insert.
  - **Internal action id** for downstream side effects (`CreditTransaction.id` is a UUIDv4 minted deterministically as `uuid5(NAMESPACE_BILLING, provider_event_id + ":" + action_kind)`). Replaying an event yields the same internal id; duplicate inserts hit a unique constraint and are swallowed.
- **At-least-once delivery semantics from both providers.** We never assume "I got this once." Handlers must be safe to replay 100 times.
- **Out-of-order delivery:** Stripe sends events in cause order but not guaranteed. RevenueCat similar. We attach `event_timestamp` (`event.created` for Stripe, `event_timestamp_ms` for RC) and apply only if it's newer than the last applied event for that `(user_id, axis)` tuple. Older events are ledger-recorded but not applied.

### 2.7 Exponential-backoff retry policies

- **Outgoing Stripe calls** (refund, customer update): retry on 5xx + 429 only, with backoff `min(2^n, 30s) + jitter(0..1s)`, max 6 attempts, then fail to dead-letter queue + page on-call.
- **Outgoing RevenueCat REST calls** (promotional grants): same pattern.
- **Inbound webhook 5xx:** Stripe and RC both retry on non-2xx. We respond `2xx` *fast* (under 5s) after the ledger insert, and process side effects async via Celery. If async processing fails, we mark the ledger row `status=retry` and a Celery Beat sweep re-tries every 60s with exponential backoff up to 24h, then dead-letter + alert.
- **Dead-letter queue:** `rabbitmq://billing.dlq.webhooks`. Manual replay tool in admin console (§016). Never auto-discard.

### 2.8 Apple IAP receipt validation via RevenueCat

- **We do not validate receipts ourselves.** RevenueCat holds Apple's shared secret and performs server-side receipt validation. RN client uses `react-native-purchases` SDK; `Purchases.purchasePackage()` returns post-validation. We get the validated entitlement state in the next `customer_info` push or via webhook.
- **Server-side trust:** never trust the client's `customer_info`; always re-fetch from RC REST or rely on the webhook event. The `GET /v1/subscribers/{user_id}` call is the source of truth at any moment.
- **Family Sharing:** Apple Family Sharing of subscriptions is supported by RC; surface in `EntitlementSnapshot.source = "family_share"` for audit.
- **Sandbox vs production:** RC handles automatically per the receipt's environment flag. Our `ENV=local|dev|staging` uses a separate RevenueCat project to avoid sandbox bleeding into prod analytics.

### 2.9 Google Play Billing via RevenueCat

- **Same shape as iOS.** RN SDK is the same `react-native-purchases`. Google sends *real-time developer notifications* (RTDN) to RC's endpoint; we never need to consume Pub/Sub directly.
- **Play-specific quirks:**
  - **Subscription upgrades/downgrades** on Play happen with proration modes (`IMMEDIATE_WITH_TIME_PRORATION` etc.). We surface only "Upgrade to Pro" / "Downgrade to Premium" / "Cancel" in UI; let Play handle proration math.
  - **`linkedPurchaseToken` chain:** when a user upgrades, the old purchase token becomes invalid; RC tracks the chain. We must not pin to a single `store_subscription_id` — keep a history.
- **Test path:** Google's *license testers* + RC's sandbox. Same separation as iOS.

### 2.10 Refund APIs

- **Apple:** No public refund API for developers to issue refunds. Mobile UX routes users to **Apple's "Report a Problem" flow** (`reportaproblem.apple.com`) per Apple's policy. Refund decisions are Apple's; we observe via RC `CANCELLATION` (with `cancellation_reason = "customer_support"`) or `REFUND` event and adjust entitlements + credit wallet accordingly.
- **Google Play:** `androidpublisher.purchases.subscriptions.refund` API exists, but Play policy steers users to in-app support → we file refund via Play Console (manual) or via API (server-to-server) **for purchases under 48h**. For >48h refunds, link to Play Help.
- **Stripe:** `refund.create({ charge: ch_xxx, amount: optional })`. Full refund for 14-day window; prorated for annual subscriptions outside window (compute proration locally: `remaining_days / total_days * paid_amount`, rounded to currency minor units, stored on `RefundRequest.computed_amount`).
- **Refund-induced cascade:** `charge.refunded` webhook → `RefundRequest.status = "approved"` → `subscription.status = "canceled"` (if it wasn't already) → `entitlement.changed` → if credits were granted as part of the refunded purchase, deduct them (possibly driving wallet negative — allow, flag for support).

### 2.11 Tax thresholds per launch geo

- **US:** No federal sales tax. State-level economic nexus thresholds vary (e.g., CA: $500k, NY: $500k + 100 tx, etc.). Stripe Tax tracks these. Finance registers state-by-state when crossed; engineering surfaces no thresholds in admin.
- **Canada:** GST/HST federally; PST/QST in some provinces (BC, SK, MB, QC). Stripe Tax handles. Threshold for non-resident GST: CAD $30k/12mo — finance to register.
- **Australia:** GST 10% on digital services to AU consumers. Threshold AUD $75k/12mo. Stripe Tax handles.
- **New Zealand:** GST 15% on remote services to NZ consumers. Threshold NZD $60k/12mo. Stripe Tax handles.
- **India:** GST 18% on OIDAR services to non-business consumers. **No threshold for foreign suppliers — must register from rupee one.** This is the spiky one. Options:
  1. Register as a foreign OIDAR taxpayer in India (Stripe Tax supports filing).
  2. Use Paddle as Merchant of Record for India only — Paddle handles GST registration + remittance.
  3. **Geofence India out at launch.** Conflicts with the master spec's GEO-1 ("US, CA, AU, NZ, IN at launch"). Don't pick this without going back to product.
- Captured as open risk §16.

---

## 3. Tier + entitlement axes

> **All values below are placeholders.** Real values live in `EntitlementConfig` (admin-edited via §016). The *schema* of axes + their *types* + their *defaults if config is missing* are what this plan locks.

### 3.1 Axes catalogue

| Axis key | Type | Unit / Range | Free (placeholder) | Premium (placeholder) | Pro (placeholder) | Consuming service |
|---|---|---|---|---|---|---|
| `invites_per_week` | int | count, -1=unlimited | 5 | -1 | -1 | invite-svc (§006) |
| `ai_credits_per_month` | int | credits | 0 | 200 | 1000 | ai-orchestrator-svc (§012) |
| `ads_shown` | bool | y/n | true | false | false | feed/ads-svc (deferred) |
| `chat_export` | bool | y/n | false | true | true | chat-svc / export (§007/§009) |
| `hide_from_non_premium` | bool | y/n | false | true | true | discovery-svc (§005) |
| `picked_for_you_priority` | enum | none/standard/high | none | standard | high | matching-svc (§004) |
| `mockup_fidelity` | enum | off/basic/advanced | off | basic | advanced | ai-orchestrator-svc (§012) |
| `portfolio_pdf_export` | bool | y/n | false | false | true | profile-svc / export |
| `visibility_boost` | bool | y/n | false | false | true | discovery-svc |
| `support_priority` | enum | std/fast/fastest | std | fast | fastest | support-svc (§014) |
| `see_who_saved_you` | bool | y/n | false | true | true | discovery-svc |
| `feed_profiles_per_day` | int | count, -1=unlimited | 30 | -1 | -1 | discovery-svc |
| `daily_save_cap` | int | count, -1=unlimited | 50 | -1 | -1 | discovery-svc |

(`feed_profiles_per_day` and `daily_save_cap` are added from FR-B-2 + R28; rounding out the axes list.)

### 3.2 Axis type system

- `bool` — JSON `true|false`.
- `int` — JSON integer; `-1` always means "unlimited".
- `enum` — JSON string; allowed values declared in code in a frozen `Literal`-typed `AXIS_REGISTRY`. Admin UI renders a dropdown from this.
- No floats. No nullable. No "TBD" values in production config.

### 3.3 Defaults if config missing

If `EntitlementConfig` for an axis is missing for a tier, **fall back to the Free-tier value in the seed migration** (above table). Log a warning and emit `entitlement_config.missing` metric. Never crash a hot-path read because config is missing.

### 3.4 Per-user overrides + grants

Beyond tier-driven values, `EntitlementSnapshot` can carry:

- **`source = "grant"`** — admin-issued override (e.g., support comp for an outage). Carries `expires_at`. Takes precedence over tier value.
- **`source = "promo"`** — promo-code grant. Same shape, separate origin for audit.

Precedence order on read: `grant` > `subscription` > `default`. Within `grant`, higher value (numerically or by enum rank) wins if multiple are active. Expirations are evaluated at read time *and* on a Celery Beat sweep every 5 min to fire `entitlement.changed`.

---

## 4. Detailed data model

All tables in schema `billing`. UUIDs unless noted. Timestamps `timestamptz`, UTC. Money in **minor units** (cents) + ISO-4217 currency code; no floats anywhere near money.

### 4.1 `Customer`

```
id                     uuid pk
user_id                uuid not null unique  -- FK auth.users (logical; no cross-schema FK)
stripe_customer_id     text null unique      -- cus_xxx; null until first web touch
revenuecat_user_id     text not null         -- == user_id; redundant for clarity
preferred_currency     char(3) not null      -- ISO-4217; geolocated at signup, user-changeable
country                char(2) not null      -- ISO-3166-1 alpha-2
tax_id                 text null             -- collected at checkout; e.g. GSTIN, ABN
tax_id_type            text null             -- 'in_gst', 'au_abn', 'ca_bn', etc.
created_at             timestamptz not null default now()
updated_at             timestamptz not null default now()
```

Index: `(stripe_customer_id)`, `(country, preferred_currency)`.

### 4.2 `Subscription`

```
id                       uuid pk
user_id                  uuid not null
source                   text not null check (source in ('stripe','revenuecat'))
gateway                  text not null check (gateway in ('stripe','apple','google','paddle_in'))
tier                     text not null check (tier in ('free','premium','pro'))
status                   text not null check (status in (
                            'trialing','active','past_due','grace','paused',
                            'canceled','expired'))
store_subscription_id    text null              -- stripe sub_xxx OR apple original_tx_id OR play purchaseToken-chain id
store_product_id         text not null          -- price_id (Stripe) OR product_id (Apple/Play)
billing_period           text not null check (billing_period in ('month','year'))
current_period_start     timestamptz not null
current_period_end       timestamptz not null
cancel_at_period_end     boolean not null default false
trial_end                timestamptz null
started_at               timestamptz not null
canceled_at              timestamptz null
ended_at                 timestamptz null       -- when status -> expired
paused_reason            text null              -- 'moderation' | 'user' (Play allows user pause)
paused_at                timestamptz null
metadata                 jsonb not null default '{}'
created_at               timestamptz not null default now()
updated_at               timestamptz not null default now()
```

Index: `(user_id, status)`, `(store_subscription_id)`, partial idx on `(user_id) where status in ('trialing','active','past_due','grace')`.

**Crucial:** a user can have **multiple rows** (one per platform). The "highest-tier wins" resolution happens in code at entitlement evaluation time. We do not collapse rows; we keep history.

### 4.3 `EntitlementSnapshot`

```
id            uuid pk
user_id       uuid not null
axis_key      text not null
value         jsonb not null            -- typed per AXIS_REGISTRY
source        text not null check (source in ('default','subscription','grant','promo'))
source_ref    uuid null                 -- subscription_id OR grant_id
expires_at    timestamptz null
updated_at    timestamptz not null default now()
created_at    timestamptz not null default now()
```

Unique: `(user_id, axis_key, source, source_ref)` — multiple sources allowed; precedence in read path.
Index: `(user_id)`, `(expires_at) where expires_at is not null`.

**Hot path:** `GET /billing/entitlements` reads this table for the calling user, applies precedence, returns a flat `{axis_key: value}` dict. Cached in Redis under `entitlements:{user_id}` with TTL 1h, invalidated by `entitlement.changed`.

### 4.4 `CreditWallet`

```
user_id      uuid pk
balance      bigint not null default 0   -- credits (integers, no fractional credit)
updated_at   timestamptz not null default now()
```

**Balance is a denormalized cache.** Source of truth is the sum of `CreditTransaction.delta`. A nightly reconciliation Celery job verifies and alerts on drift.

### 4.5 `CreditTransaction`

```
id                uuid pk
user_id           uuid not null
delta             bigint not null              -- +N for credit, -N for debit, can be negative
reason            text not null check (reason in (
                    'purchase','admin_grant','subscription_grant',
                    'consume','reserve','release','refund','expire'))
reference_kind    text not null                -- 'stripe_charge' | 'rc_event' | 'ai_interaction' | 'admin_action'
reference_id      text not null
idempotency_key   text not null                -- deterministic per source event
status            text not null check (status in ('reserved','committed','released','reversed'))
                                                default 'committed'
created_at        timestamptz not null default now()
committed_at      timestamptz null
```

Unique: `(idempotency_key)`. Index: `(user_id, created_at desc)`, `(status) where status='reserved'`.

**Reservation pattern:**
- `reserve`: row with `delta = -N`, `status = 'reserved'`. Balance check rejects if `balance + sum(reserved deltas) < 0`.
- `commit`: update `status -> 'committed'`, set `committed_at`.
- `release` (on failure): update `status -> 'released'`, write a compensating `+N` transaction with `reason = 'release'` and `reference_id = original.id`.

All wallet writes inside a `SERIALIZABLE` transaction with row-level lock on `CreditWallet.user_id`. (See §9.)

### 4.6 `Invoice`

```
id                    uuid pk
user_id               uuid not null
stripe_invoice_id     text null unique         -- in_xxx (web only; mobile invoices live in store)
rc_event_id           text null unique         -- for mobile-originated charges
amount_minor          bigint not null
currency              char(3) not null
tax_minor             bigint not null default 0
status                text not null check (status in (
                        'draft','open','paid','uncollectible','void','refunded','partial_refund'))
period_start          timestamptz null
period_end            timestamptz null
hosted_invoice_url    text null                -- Stripe-hosted; for mobile, null
pdf_url               text null
created_at            timestamptz not null default now()
updated_at            timestamptz not null default now()
```

### 4.7 `RefundRequest`

```
id                   uuid pk
user_id              uuid not null
kind                 text not null check (kind in ('subscription','credit_purchase'))
subscription_id      uuid null
transaction_id       uuid null                       -- CreditTransaction.id when kind='credit_purchase'
invoice_id           uuid null
requested_at         timestamptz not null default now()
within_14d           boolean not null
reason_user          text null                       -- free-text from user
reason_internal      text null                       -- internal note (admin)
status               text not null check (status in (
                        'auto_approved','pending','approved','denied',
                        'routed_to_apple','routed_to_google'))
                       default 'pending'
decided_at           timestamptz null
decided_by           uuid null                       -- admin user id
refund_amount_minor  bigint null
refund_currency      char(3) null
stripe_refund_id     text null
created_at           timestamptz not null default now()
updated_at           timestamptz not null default now()
```

### 4.8 `WebhookEventLedger`

```
id                   bigserial pk
provider             text not null check (provider in ('stripe','revenuecat'))
provider_event_id    text not null
event_type           text not null
event_timestamp      timestamptz not null
payload              jsonb not null
signature_valid      boolean not null
status               text not null check (status in ('received','processing','done','retry','dead'))
                       default 'received'
attempts             int not null default 0
last_error           text null
received_at          timestamptz not null default now()
processed_at         timestamptz null
```

Unique: `(provider, provider_event_id)`.
Index: `(status, received_at) where status in ('received','retry')`.

### 4.9 `DunningCase`

```
id                     uuid pk
user_id                uuid not null
subscription_id        uuid not null
opened_at              timestamptz not null
state                  text not null check (state in (
                          'day0','day3','day7','day10_canceled','day30_grace_expired','recovered'))
last_attempt_at        timestamptz null
last_attempt_result    text null
last_email_sent_at     timestamptz null
recovered_at           timestamptz null
closed_at              timestamptz null
```

Index: `(state, opened_at)` for Celery Beat scheduler.

---

## 5. Subscription state machine

```
                       (purchase)                (trial end + paid)
   [none] -------------------------> [trialing] -----------------------> [active]
                                          |                                  |
                                  (trial end + fail)                  (renew fail)
                                          v                                  v
                                     [past_due] <---------------------- [past_due]
                                          |                                  ^
                                  (dunning recovers)                        |
                                          v                                  |
                                       [active]                              |
                                          |                                  |
                                   (dunning fails day10)                     |
                                          v                                  |
                                     [canceled] ---(within 30d grace)---> [grace]
                                          |                                  |
                                  (period_end reached                  (user re-pays
                                   without re-pay)                       in grace)
                                          v                                  v
                                      [expired]                          [active]

       (admin/moderation pause)             (user-initiated pause on Play)
   [active] -----------------------> [paused] <-------------------------
                                          |
                                  (resume)
                                          v
                                       [active]
```

State definitions:

- **`trialing`** — paid signup with a free trial window. Entitlements granted at tier level. Cancellation during trial → `canceled` immediately, period ends at trial end with no charge.
- **`active`** — paid, current.
- **`past_due`** — charge failed on or after `current_period_end`; entitlements **remain** at tier level for the dunning window (we don't yank features during the retry phase). Set on Stripe `invoice.payment_failed` or RC `BILLING_ISSUE`.
- **`grace`** — `canceled` but within 30-day reactivation window (master spec FR-E-6). Entitlements **drop to Free** at `canceled_at`, but reactivation restores tier without re-onboarding payment if within 30d.
- **`paused`** — admin or moderation-initiated. Two sub-causes:
  - `paused_reason = "moderation"` — user is temp-muted/banned (§008). Subscription clock **stops**; on unban it resumes with the remaining period_end shifted by pause duration. Entitlements drop to Free during pause. Stripe: `subscription.pause_collection`. RC: there's no first-class server-side pause, so we set `Subscription.status = 'paused'` in our table and stop honoring entitlements; we do **not** refund the user — the time is added back on unban. **Open caveat** (§16): for an Apple/Play sub we cannot pause the user's recurring billing; if the moderation pause exceeds the next renewal, we let it renew, log the duration, and credit them after.
  - `paused_reason = "user"` — Play allows user-initiated subscription pause for 1 week / 1 month / 3 months. iOS does not. Web: not supported in UI.
- **`canceled`** — user canceled or dunning gave up. No more charges. Entitlements at Free.
- **`expired`** — period ended without recovery. Final state.

Transitions are written **only** by webhook handlers + the dunning state machine. Direct admin override available (§016) but always writes a `Subscription_audit_log` row.

---

## 6. Cross-platform entitlement parity

### 6.1 Source-of-truth choice

**RevenueCat is the read-side source of truth for entitlements.** Stripe is the source of truth for *web charges*. RevenueCat's Stripe-as-Backend integration projects Stripe subscriptions into RC's subscriber model. Our `billing-svc` then keeps a *local denormalized view* in `Subscription` + `EntitlementSnapshot` so we can serve `GET /billing/entitlements` at <50ms P95 without an RC roundtrip.

### 6.2 Sequence: user buys on iOS

```
RN client                Apple StoreKit         RevenueCat              billing-svc            other services
   |                          |                     |                       |                        |
   |--purchasePackage()------>|                     |                       |                        |
   |                          |--receipt----------->|                       |                        |
   |                          |                     |--validate w/ Apple--->|                        |
   |                          |                     |<----result------------|                        |
   |<--customer_info----------|<--------------------|                       |                        |
   |                                                |                       |                        |
   |                                                |--webhook INITIAL_PURCHASE----->|                |
   |                                                |   {app_user_id, entitlements}  |                |
   |                                                |                                | (verify sig)   |
   |                                                |                                | (ledger insert)|
   |                                                |                                | upsert Subscription
   |                                                |                                | upsert Entitlement
   |                                                |                                | publish entitlement.changed
   |                                                |                                |---------AMQP--->|
   |                                                |                                |                | (invalidate cache)
   |--GET /entitlements----------------------------->|                                |                |
   |<-------------------------- {invites: -1, ai_credits: 200, ...} ------------------|                |
```

### 6.3 Sequence: user buys on web (Stripe)

```
Next.js consumer-web       billing-svc           Stripe              RevenueCat          other services
   |                           |                    |                    |                    |
   |--POST /checkout/web------>|                    |                    |                    |
   |                           |--Session.create--->|                    |                    |
   |                           |  client_ref=uid    |                    |                    |
   |                           |  automatic_tax=on  |                    |                    |
   |                           |<--session.url------|                    |                    |
   |<--{url}-------------------|                    |                    |                    |
   |--redirect to Stripe------>|                                          |                    |
   |  (user pays)                                                         |                    |
   |                                                                      |                    |
   |                                              [webhook] checkout.session.completed
   |                                              [webhook] customer.subscription.created
   |                                              [webhook] invoice.paid
   |                                                |                    |                    |
   |                              <-- both billing-svc and RC are subscribed to Stripe -->     |
   |                           |<--webhook----------|                                          |
   |                           | upsert Subscription                                           |
   |                           |                    |--projection------->|                    |
   |                           |                                          |--RC webhook-->|    |
   |                           |                                                          |    |
   |                           |  (RC webhook handler is a no-op for status if already set,
   |                           |   but updates EntitlementSnapshot with source='subscription'
   |                           |   and rc-derived expiry; idempotent)
   |                           |
   |                           |--publish entitlement.changed-->|
```

### 6.4 Mixed-platform user (iOS sub + web sub)

Real scenario: user buys Premium on iOS, then later buys Pro on web. Or vice versa. **No platform deduplication is attempted** — that's an App Store policy minefield. Resolution:

1. Both `Subscription` rows exist in our DB.
2. At entitlement evaluation, we pick the **highest tier** among rows with status in `{trialing, active, past_due, grace}`.
3. Among rows of the same tier, we pick the row with the **latest `current_period_end`**.
4. We write a single `EntitlementSnapshot` per axis with `source_ref` pointing to the winning subscription.
5. We **surface in the account screen** that the user has duplicate subscriptions on two platforms and link to cancellation instructions for the *lower-tier or earlier-expiring* one. We do NOT auto-cancel.
6. Refunds: each subscription is refundable independently via its own platform's flow.

### 6.5 Logout / device switch

`Purchases.logOut()` on RN client when user logs out. Pre-login purchases are anonymized RC ids; we don't honor them. UI explicitly says "Log in before purchasing."

---

## 7. Dunning state machine

Triggered by `invoice.payment_failed` (Stripe) or `BILLING_ISSUE` (RC).

### 7.1 States + transitions

| State | Entered when | Actions | Next state on success | Next state on continued failure | Timer |
|---|---|---|---|---|---|
| `day0` | First payment failure | Retry charge immediately (Stripe Smart Retries handles for web; RC handles for mobile). Send email: "We couldn't charge your card." Subscription.status = `past_due`. | `recovered` | `day3` | +3 days |
| `day3` | 3 days after `day0` and still failed | Retry charge. Email: "Try again to keep Premium." | `recovered` | `day7` | +4 days |
| `day7` | 7 days after `day0` and still failed | Retry charge. Email: "Final reminder — your subscription will be canceled in 3 days." | `recovered` | `day10_canceled` | +3 days |
| `day10_canceled` | 10 days after `day0` and still failed | Cancel subscription (Stripe `subscription.cancel`; RC sends EXPIRATION). Email: "Your Premium is canceled." Subscription.status = `canceled`. Entitlements drop to Free. Open 30-day grace window. | `recovered` (if user re-subscribes within 30d → `active`) | `day30_grace_expired` | +20 days |
| `day30_grace_expired` | 30 days after `day10_canceled` and no re-sub | Subscription.status = `expired`. Email: "We hope to see you again." | (none) | (none) | terminal |
| `recovered` | Any time user pays | Email: "Thanks — you're all set." Close DunningCase. | (none) | (none) | terminal |

### 7.2 Implementation

- Celery Beat job `dunning_tick` runs every 10 minutes; picks open `DunningCase` rows whose `last_attempt_at + state_delay < now()` and advances.
- For Stripe: we **also** rely on Stripe Smart Retries — set retry schedule in Stripe Dashboard to align (day 0, 3, 7, 10). Stripe's `invoice.payment_succeeded` event collapses the DunningCase to `recovered` regardless of our own scheduling.
- For mobile: RC handles retries internally per Apple/Play rules (Apple retries for ~60 days; Play similar). We track the **logical** dunning state from the events RC sends us (`BILLING_ISSUE` → start; `RENEWAL` after issue → recovered; `EXPIRATION` → canceled). Our day0/3/7/10 model is approximate for mobile.
- Emails sent via SES, templated. Suppression list honored. Receipts always sent regardless of marketing pref (transactional).

---

## 8. Refund flow

### 8.1 Decision matrix

| Platform | <14d since purchase | >14d, annual | >14d, monthly |
|---|---|---|---|
| Stripe (web) | Auto-approve, full refund via `refund.create` | Pro-rate, manual admin review | Deny, link to next-period cancel |
| Apple (iOS) | Route to `reportaproblem.apple.com`; observe RC event | Same | Same |
| Google Play (Android) | Auto-approve via Play API if <48h; else route to support | Manual admin review | Deny, link to cancel |
| Credit bundle (Stripe) | Full refund if no credits consumed since purchase | Manual admin review | Manual admin review |

### 8.2 Sequence: web auto-approve

1. User clicks "Refund" in account screen.
2. `POST /billing/refund-request` with `subscription_id` (or `transaction_id` for credit bundle).
3. Service computes `within_14d` from the source charge timestamp.
4. If `within_14d` AND `source == 'stripe'`:
   - Idempotency-key = `refund:{subscription_id}:{user_id}`.
   - Call `stripe.Refund.create(charge=..., reason='requested_by_customer')`.
   - Record `RefundRequest.status = 'auto_approved'`, store `stripe_refund_id`.
   - Wait for `charge.refunded` webhook → finalize: cancel subscription, drop entitlements, deduct credits proportionally if any granted from this charge.
5. Email user: "Refunded $X. Subscription canceled."

### 8.3 Sequence: mobile route-to-support

1. User clicks "Refund" in account screen on RN.
2. Client routes based on platform:
   - iOS → deep-link to `https://reportaproblem.apple.com/?s=<order>`.
   - Android → deep-link to Play Help with the original purchase token.
3. Server records `RefundRequest.status = 'routed_to_apple' | 'routed_to_google'` so the case shows up in admin support queue for follow-up.
4. When the store actually refunds, RC sends `CANCELLATION` (`reason=customer_support`) or a dedicated `REFUND` event; we update `RefundRequest.status = 'approved'` and adjust entitlements/credits.

### 8.4 Admin override

`POST /admin/refunds/{id}/decide` body `{decision: approve|deny, internal_note}`. Approve = same Stripe flow; deny = email user with reason. All admin actions to `AdminAuditLog` (§016).

---

## 9. Credit wallet semantics

### 9.1 Pessimistic reservation for AI commands

§012 calls `billing-svc` *before* invoking Replicate:

```
POST /credits/reserve
{
  user_id,
  amount: N,                         -- per-command cost from EntitlementConfig (admin-tunable)
  reference_kind: 'ai_interaction',
  reference_id: <interaction_uuid>
}
```

`billing-svc`:

1. Open `SERIALIZABLE` tx.
2. `SELECT balance FROM CreditWallet WHERE user_id = ? FOR UPDATE`.
3. Compute `available = balance - sum(reserved deltas for this user)`. If `available < N`, return 402.
4. Insert `CreditTransaction { delta: -N, status: 'reserved', reason: 'reserve', reference_kind: 'ai_interaction', reference_id, idempotency_key }`.
5. Commit. Return `{ reservation_id }`.

Then §012 runs Replicate.

- On success: `POST /credits/commit { reservation_id }` → status `reserved -> committed`, update `CreditWallet.balance -= N` materialization.
- On failure: `POST /credits/release { reservation_id }` → status `reserved -> released`, write a compensating `+N` transaction with `reason='release'`. Balance untouched (net zero).

**Stale reservation sweep:** Celery Beat job `release_stale_reservations` every 5 min — any `status='reserved'` older than 15 min is auto-released. Logs alert if any user repeatedly has stale reservations (possible §012 bug).

### 9.2 Idempotency on top-up

- Web purchase: Stripe `checkout.session.completed` webhook → derive `idempotency_key = "purchase:" + session_id`. Insert `CreditTransaction { delta: +N, reason: 'purchase', idempotency_key, status: 'committed' }`. Unique constraint dedupes replay.
- Mobile purchase: RC `NON_RENEWING_PURCHASE` webhook → `idempotency_key = "purchase:" + rc_event_id`. Same flow.

### 9.3 Subscription-based monthly credit grant

On `subscription.activated` and on every `RENEWAL`:

- Insert `CreditTransaction { delta: +ai_credits_per_month, reason: 'subscription_grant', idempotency_key: "grant:" + sub_id + ":" + period_start, expires_at: period_end }`.
- We do **not** expire un-used granted credits this milestone (they roll over). Future axis: `credits_rollover_enabled` bool.

### 9.4 Reconciliation

Nightly `wallet_reconciliation` job: for each `CreditWallet`, recompute `balance = sum(delta) where status='committed'`. Compare to `CreditWallet.balance`. If drift > 0, log + Sentry alert, do **not** auto-fix; surface in admin.

---

## 10. Tax

### 10.1 Stripe Tax — web

- All Checkout sessions: `automatic_tax: { enabled: true }`.
- All Subscription updates from server: same.
- `tax_id_collection: { enabled: true }` on Checkout for B2B refunds + GSTIN capture.
- Tax codes per product configured in Stripe Dashboard at infra bootstrap (P0): SaaS sub = `txcd_10103000`; credit bundle = `txcd_10000000` (digital goods). Final codes locked at Phase 5b.
- Origin: US (Colab legal entity). Stripe Tax origin address set once.

### 10.2 RevenueCat / store-handled — mobile

- Apple and Google both calculate tax and remit on our behalf in all five launch geos. RevenueCat surfaces "tax included" in events.
- We **do not** invoice tax for mobile purchases; the receipts in the App Store / Play history are authoritative.
- Our `Invoice.tax_minor` for mobile rows = informational only (from RC event).

### 10.3 India GST

- Default plan: register Colab as a foreign OIDAR taxpayer with India GSTIN; Stripe Tax files. Requires legal entity setup + ~6 weeks lead time. **Decision needed at Phase 5b finance review.**
- Fallback: Paddle MoR for India only. `Subscription.gateway = 'paddle_in'` accommodated in schema. Paddle integration is a separate implementation task **not** in scope this plan unless India OIDAR path is rejected; flagged in §16.
- Either way, mobile India IAP is store-handled (Apple/Google remit local GST automatically); only web is the question.

### 10.4 Per-region tax-id collection

- US: no national tax ID; states differ. Skip on Checkout (Stripe Tax handles).
- CA: GST/HST number (`ca_gst_hst`) optional collection.
- AU: ABN (`au_abn`) optional.
- NZ: GST number (`nz_gst`) optional.
- IN: GSTIN (`in_gst`) collected for B2B; absent = B2C.

---

## 11. Webhook handling

### 11.1 Common pipeline

```
[HTTP] POST /webhooks/{provider}
    -> verify signature (provider-specific; constant-time)
    -> insert into WebhookEventLedger (unique on provider_event_id)
        -> if duplicate: return 200 immediately (no further work)
    -> publish Celery task `process_webhook_event(ledger_id)`
    -> return 200 within <5s
```

Async task `process_webhook_event`:

```
load ledger row
mark status = 'processing'
dispatch to event-type-specific handler:
    stripe.checkout.session.completed -> handle_checkout_completed
    stripe.customer.subscription.created -> handle_sub_created
    stripe.customer.subscription.updated -> handle_sub_updated
    stripe.customer.subscription.deleted -> handle_sub_canceled
    stripe.invoice.paid -> handle_invoice_paid
    stripe.invoice.payment_failed -> handle_invoice_failed
    stripe.charge.refunded -> handle_charge_refunded
    revenuecat.INITIAL_PURCHASE -> handle_rc_initial_purchase
    revenuecat.RENEWAL -> handle_rc_renewal
    revenuecat.CANCELLATION -> handle_rc_cancellation
    revenuecat.EXPIRATION -> handle_rc_expiration
    revenuecat.BILLING_ISSUE -> handle_rc_billing_issue
    revenuecat.NON_RENEWING_PURCHASE -> handle_rc_one_off
    revenuecat.SUBSCRIBER_ALIAS -> handle_rc_alias_merge
    revenuecat.PRODUCT_CHANGE -> handle_rc_product_change
on success: status='done', processed_at=now
on exception: attempts++, status='retry' (or 'dead' after N attempts)
```

### 11.2 Signature verification

- **Stripe:** `stripe.Webhook.construct_event(body, sig_header, STRIPE_WEBHOOK_SECRET)`. SDK handles timestamp tolerance (5 min default). Reject if invalid.
- **RevenueCat:** compare `Authorization` header to `REVENUECAT_WEBHOOK_SECRET` (constant-time). Body is JSON; no HMAC.

### 11.3 Replay-safety

- Unique key on `(provider, provider_event_id)`. Replay → ledger insert fails → return 200 (we already processed).
- Each handler **also** uses event-derived idempotency keys for downstream writes (`CreditTransaction.idempotency_key`, etc.) so even a manual ledger re-insert is safe.

### 11.4 Out-of-order handling

Each event carries a timestamp. Handlers check `event_timestamp >= subscription.updated_at` before applying state transitions. Older events are recorded but not applied. Logs include `"event_skipped_stale": true` for observability.

---

## 12. API contracts

OpenAPI specs codegen-driven from `billing-svc/api/openapi.yaml` (sketched here in shorthand; full YAML in `billing-svc/api/` at implementation time).

### 12.1 Public (authenticated user)

#### `GET /billing/entitlements`
- Response: `{ axes: { invites_per_week: -1, ai_credits_per_month: 200, ... }, tier: 'premium', subscription_status: 'active', current_period_end: '...' }`.
- Cached. Invalidated by `entitlement.changed`.

#### `GET /billing/subscriptions`
- Response: list of `Subscription` rows (one per platform). Excludes internal metadata.

#### `POST /billing/checkout/web`
- Body: `{ price_id: 'STRIPE_PRICE_ID_PREMIUM_MONTH', return_url, cancel_url }`.
- Validates `price_id` is in our `EntitlementConfig`-linked allowlist.
- Returns: `{ checkout_url, session_id }`.
- Errors: 400 unknown price; 409 user already has active sub of same-or-higher tier.

#### `GET /billing/credits/balance`
- Response: `{ balance: 153 }`.

#### `POST /billing/credits/purchase/web`
- Body: `{ price_id, return_url }`. Validates price is a credit bundle.
- Returns: `{ checkout_url, session_id }`.

#### `POST /billing/cancel/web`
- Body: `{ subscription_id, immediate: bool }`.
- `immediate=false` → `cancel_at_period_end=true` on Stripe; entitlements stay until period end.
- `immediate=true` → cancel now; route to `/refund-request` if within 14d (UI sends both calls).

#### `POST /billing/refund-request`
- Body: `{ subscription_id?, transaction_id?, reason }`.
- Returns: `{ refund_request_id, status, refund_amount_minor?, currency?, routed_to?: 'apple'|'google' }`.

### 12.2 Internal (service-to-service, mTLS-only)

#### `POST /internal/credits/reserve`
- Body: `{ user_id, amount, reference_kind, reference_id }`.
- Returns: `{ reservation_id }` or 402 `{ error: 'insufficient_credits', balance, requested }`.

#### `POST /internal/credits/commit`
- Body: `{ reservation_id }`.
- Returns: 204.

#### `POST /internal/credits/release`
- Body: `{ reservation_id, reason }`.
- Returns: 204.

#### `GET /internal/entitlements/{user_id}`
- Same shape as public, but for any user. Used by other services that need to check entitlements server-side.

### 12.3 Webhooks (provider-to-server)

#### `POST /webhooks/stripe`
- Headers: `Stripe-Signature`.
- Returns: 200 on accept (incl. duplicate); 400 on signature failure.

#### `POST /webhooks/revenuecat`
- Headers: `Authorization`.
- Returns: 200 on accept; 401 on signature failure.

### 12.4 Admin (admin-svc-facing)

#### `GET /admin/billing/users/{user_id}/360`
- Subscription history, invoices, credit transactions, refund requests, dunning case.

#### `POST /admin/billing/refunds/{id}/decide`
- Body: `{ decision: 'approve'|'deny', internal_note }`.

#### `POST /admin/billing/grants`
- Body: `{ user_id, axis_key, value, expires_at?, reason }`. Writes `EntitlementSnapshot` with `source='grant'`.

#### `POST /admin/billing/credit-adjustment`
- Body: `{ user_id, delta, reason }`. Writes `CreditTransaction { reason: 'admin_grant' }`.

#### `PUT /admin/billing/tier-config`
- Body: `{ tier, axis_key, value }`. Writes `EntitlementConfig`. Broadcasts `entitlement.changed` to all users of that tier (carefully batched).

### 12.5 Queue events (publish)

| Event | Payload | Subscribers |
|---|---|---|
| `entitlement.changed` | `{ user_id, axis_keys?: [], tier? }` | discovery-svc, invite-svc, ai-orchestrator-svc, chat-svc (caches) |
| `credits.consumed` | `{ user_id, amount, reference }` | analytics-svc |
| `credits.purchased` | `{ user_id, amount, source, reference }` | analytics-svc |
| `credits.granted` | `{ user_id, amount, reason }` | analytics-svc |
| `subscription.activated` | `{ user_id, tier, source }` | notification-svc, analytics-svc |
| `subscription.canceled` | `{ user_id, tier }` | notification-svc, analytics-svc |
| `subscription.past_due` | `{ user_id, tier }` | notification-svc |
| `refund.granted` | `{ user_id, amount }` | notification-svc, analytics-svc, support-svc |

---

## 13. Implementation tasks

| id | title | outcome | est_hours | blocks | blocked_by |
|---|---|---|---:|---|---|
| T-001 | Provision Stripe + RC accounts | Test+live keys in Secrets Manager; webhook endpoints registered; tax codes set; API version pinned | 6 | T-002, T-003, T-010 | P0 infra |
| T-002 | Configure Stripe Tax | Origin set; tax codes per product; automatic_tax enabled in Checkout templates | 4 | T-011 | T-001 |
| T-003 | Configure RC project | iOS + Android + Stripe-as-Backend linked; entitlements + offerings + product mapping | 6 | T-013 | T-001 |
| T-004 | Bootstrap `billing-svc` skeleton | FastAPI scaffold, DB migrations dir, RabbitMQ pub, Redis cache, OpenAPI codegen wired | 8 | T-005..T-022 | shared platform |
| T-005 | Migrations: Customer/Subscription/EntitlementSnapshot/CreditWallet/CreditTransaction/Invoice/RefundRequest/WebhookEventLedger/DunningCase | All tables, indexes, constraints applied in dev DB | 10 | many | T-004 |
| T-006 | `AXIS_REGISTRY` + `EntitlementConfig` seed | Axis catalogue locked in code with type validators; seed migration for Free/Premium/Pro placeholders | 6 | T-007, T-008 | T-005 |
| T-007 | Entitlement read API (`GET /billing/entitlements`) | <50ms P95 with Redis cache; precedence rules correct | 10 | many | T-006 |
| T-008 | Internal entitlement consumer SDK | Python `billing_client` + TS client for RN/web; one-call API to fetch + cache | 6 | other services | T-007 |
| T-009 | Customer onboarding lazy-create | First webhook/checkout creates Stripe + RC linkage; idempotent | 4 | T-010, T-013 | T-005 |
| T-010 | Stripe Checkout web flow | `POST /billing/checkout/web` returns URL; `automatic_tax`; `client_reference_id`; `tax_id_collection` | 10 | T-011 | T-009 |
| T-011 | Stripe webhook handler | Signature verify; ledger insert; dispatch table; handlers for sub create/update/delete/invoice paid/failed/charge refunded | 20 | T-014, T-016, T-018 | T-005, T-010 |
| T-012 | RC webhook handler | Signature verify; ledger insert; dispatch table; handlers for INITIAL_PURCHASE/RENEWAL/CANCELLATION/EXPIRATION/BILLING_ISSUE/NON_RENEWING_PURCHASE/PRODUCT_CHANGE/SUBSCRIBER_ALIAS | 20 | T-014, T-016 | T-005 |
| T-013 | RC client integration in RN | `Purchases.configure`, `logIn` on auth, paywall surface for IAP | 12 | T-019 | T-003, RN base |
| T-014 | Subscription state machine | Transitions per §5; audit log; precedence resolver for multi-platform | 14 | T-007 | T-011, T-012 |
| T-015 | Cross-platform parity resolver | Highest-tier-wins, latest-period-end tiebreaker; duplicate-sub UI notice | 6 | T-019 | T-014 |
| T-016 | Credit wallet ops | Reservation pattern with serializable tx; internal endpoints; nightly reconciliation | 14 | T-017, §012 | T-005 |
| T-017 | Credit purchase flow (web + mobile) | Stripe one-off Checkout for bundles; RC NON_RENEWING_PURCHASE handler; idempotent | 10 | T-019 | T-010, T-012, T-016 |
| T-018 | Dunning state machine | DunningCase rows; Celery Beat tick; emails via SES; recovery detection | 12 | T-019 | T-011, T-012 |
| T-019 | Account/billing UI (RN + web) | Tier display, usage history, cancel, refund-request, credit balance, top-up | 24 | none | T-013, T-007 |
| T-020 | Refund flow | `POST /billing/refund-request`; auto-approve <14d via Stripe; route mobile to store; admin override | 14 | none | T-011, T-012, T-019 |
| T-021 | Admin endpoints + console wiring | `/admin/billing/*` endpoints; admin-web surfaces; audit log | 16 | §016 | T-005..T-020 |
| T-022 | Webhook replay / dead-letter tooling | Admin tool to replay ledger rows; DLQ inspector | 8 | none | T-011, T-012 |
| T-023 | India GST decision + implementation | Either Stripe OIDAR registration or Paddle integration; schema gateway field already supports both | 24 (Paddle) / 6 (Stripe-only) | none | finance decision |
| T-024 | Load + chaos test suite | Webhook flood, double-charge attempts, replay attacks; runs in CI | 12 | release gate | T-011..T-018 |
| T-025 | Observability + alerts | Sentry breadcrumbs; CloudWatch metrics; alarms on DLQ depth, reconciliation drift, signature failures | 8 | release gate | T-011..T-018 |

Total est: ~284 hours (~7 engineer-weeks for one senior + reviews); excludes T-023 Paddle path.

---

## 14. Test strategy

### 14.1 Unit

- Axis precedence resolver: every combination of `default + subscription + grant + promo` with various expiries.
- Tier resolver (highest-wins): every pair of platform statuses.
- Refund proration math: each currency, each period split, rounding behavior.
- Idempotency-key derivation: same input → same key; different input → different key.
- Webhook signature verification: valid, invalid, expired-timestamp, wrong-secret.

### 14.2 Integration

- Stripe test-mode end-to-end: checkout → webhook → entitlement → cancel → refund → webhook → entitlement.
- RC sandbox end-to-end: in-app purchase fixture → webhook → entitlement.
- Cross-platform: simulate iOS purchase then web purchase; assert highest-tier-wins.
- Credit reservation race: 100 concurrent `reserve` requests for a user with exactly enough credits for 50 → exactly 50 succeed, 50 fail with 402.

### 14.3 Replay attacks

- Replay same Stripe webhook event id 100×: only one `Subscription` write, one `CreditTransaction`, one outbound `entitlement.changed`.
- Replay an old (timestamp < current state) event: ledger records, no state change.
- Modify webhook body but keep old signature: 400.

### 14.4 Double-charge prevention

- Send two `POST /billing/checkout/web` with same `price_id` for same user within 100ms: only one Checkout Session created (server-side dedupe via `idempotency_key` derived from user_id+price_id+5-min-window).
- Stripe replays `checkout.session.completed`: only one `CreditTransaction` inserted.
- RC sends `RENEWAL` twice (real-world bug): only one credit grant.

### 14.5 Currency conversion

- User changes country US→IN mid-subscription: existing Stripe sub stays USD, new purchases in INR; `Customer.preferred_currency` flips; `Invoice` rows carry their own currency. No mixed-currency math.
- Credit bundles priced per-region in Stripe (separate Price IDs); pick at checkout based on `Customer.country`.

### 14.6 Tax-jurisdiction edge cases

- US user with billing address in a state with new economic-nexus crossing: Stripe Tax returns correct rate; verify on invoice.
- Canadian user in QC (QST + GST): both shown.
- AU user with ABN provided: B2B treatment (no GST or reverse-charge per Stripe Tax rules).
- IN user without GSTIN: B2C, 18% GST applied via Stripe Tax (if registered) or Paddle (if MoR path).
- User moves country: existing renewals use stored origin until next billing cycle; new Checkout uses new country.

### 14.7 Refund edge cases

- Refund granted then user re-subscribes: no double-grant of monthly credits.
- Refund of a credit bundle after credits consumed: wallet goes negative; flagged in admin.
- Subscription canceled in grace, refund requested: refund proportional to unused period.

### 14.8 Dunning edge cases

- User updates card on day 5 of dunning: Stripe Smart Retries succeeds → `recovered`; our day0/3/7 timers cancel.
- User cancels during past_due: jump directly to `canceled`; grace window opens.
- Card permanently declined (Apple-side decline reason): no infinite retries; expire at Apple's schedule.

### 14.9 Performance gates

- `GET /billing/entitlements` P95 <50ms under 1000 RPS warmed cache; <200ms cold.
- Webhook ingest <100ms P95 (just ledger insert + queue publish).
- Wallet reserve P95 <30ms under contention.

---

## 15. Acceptance criteria

| ID | Statement | Verification |
|---|---|---|
| AC-1 | New user starts on Free with default entitlements seeded. | Create user → `GET /billing/entitlements` returns the Free placeholders. |
| AC-2 | Mobile Premium purchase via App Store grants Premium entitlements within 5s. | RN test purchase → RC webhook fires → `GET /billing/entitlements` reflects Premium. Measured. |
| AC-3 | Web Premium purchase via Stripe grants Premium entitlements within 5s. | Stripe test-mode checkout → webhook → `GET /billing/entitlements`. Measured. |
| AC-4 | Cross-platform parity: user with iOS Pro + web Premium gets Pro entitlements. | Fixture both, assert tier=`pro`. |
| AC-5 | Credit purchase increments wallet; AI command decrements. | Buy 200, run `/mockup-image` (cost 10), wallet = 190. Reserve→commit path verified. |
| AC-6 | AI command failure refunds credits. | Force Replicate 5xx → wallet returns to 200. |
| AC-7 | Dunning: failed renewal → day0 email + retry; recovers within 10 days; otherwise canceled. | Stripe test-mode payment_failed fixture; advance Celery Beat clock; verify state transitions + emails. |
| AC-8 | Grace period: canceled user re-subscribing within 30d skips re-onboarding payment. | Sequence test. |
| AC-9 | Refund within 14d auto-approves. | `POST /billing/refund-request` for a charge 5 days old → Stripe refund fired; webhook closes case. |
| AC-10 | Refund after 14d goes to admin queue (web) or store routing (mobile). | Sequence tests for each platform. |
| AC-11 | Admin can change Premium `invites_per_week` and all Premium users see new value in <60s. | Update via §016 endpoint → `entitlement.changed` broadcast → caches invalidate. Measured P95. |
| AC-12 | Webhook signature failure returns 400 and does not write ledger. | Replay test with bad signature. |
| AC-13 | Webhook replay does not double-process. | Send same event 100× → exactly one downstream side effect. |
| AC-14 | Moderation pause via §008 drops user to Free entitlements while paused. | Trigger pause → `GET /billing/entitlements` returns Free; resume → returns Premium with adjusted period. |
| AC-15 | India user on web checkout gets GST 18% on invoice. | Stripe test-mode IN address → tax line present (assuming OIDAR registered or Paddle path). Conditional on §16 decision. |
| AC-16 | Reconciliation drift detected nightly. | Insert manual drift → nightly job flags it in admin. |

---

## 16. Open risks

### 16.1 India GST registration

- **Risk:** No tax decision means India launch blocked on tax compliance. Apple/Google handle their side, but web Stripe requires either OIDAR registration (~6 weeks legal) or Paddle integration (~24 engineering hours + Paddle commercial).
- **Mitigation:** Decision needed at Phase 5b finance + legal review. Schema accommodates both (`gateway` field). Engineering builds Stripe-only path now; T-023 is a contingency.
- **Worst case:** Geofence India out of web at launch (mobile still works). Conflicts with GEO-1; requires re-clarification with product.

### 16.2 Subscription pause on moderation ban

- **Risk:** We cannot programmatically pause an Apple/Play recurring sub mid-period from our side. A user banned for 7 days during their billing month still gets charged on renewal. We're then on the hook to credit-back time post-unban.
- **Mitigation:** Track moderation pause duration in `Subscription.paused_at`/`resumed_at`; on resume, if a renewal happened during pause, write a `subscription_grant` credit equal to the paused days proportionally, OR extend `current_period_end` via an admin grant on the EntitlementSnapshot. Document the policy and surface in admin UI.
- **Side-effect:** A *permanently* banned user with an active sub: we cancel via Stripe (we control) and refund prorated; for Apple/Play we cancel via store APIs where available, else let the sub expire naturally and refund prorated via admin override. Customer-perception risk; document.

### 16.3 Currency drift on country change

- **Risk:** User signs up in US (USD), travels to India and updates country (INR). Existing Stripe sub charges USD; new credit purchases charge INR. The mobile sub stays in the original store currency. Account screen looks confusing.
- **Mitigation:** Explicit UI copy on account screen: "Your Premium subscription was purchased in USD and will renew in USD until you cancel and re-subscribe." Same for mobile per platform.

### 16.4 RevenueCat outage

- **Risk:** RC down → webhook gap → entitlements stale.
- **Mitigation:** Daily Celery Beat job `rc_reconciliation` calls `GET /v1/subscribers/{user_id}` for all users with `Subscription.source='revenuecat'` and reconciles. Detects gaps. Alerts.

### 16.5 Webhook replay flood (DoS)

- **Risk:** Attacker forges signatures or replays a stolen valid event 1M times.
- **Mitigation:** Signature verification + rate-limit per source IP at API Gateway. Ledger unique constraint absorbs replays at O(1) cost. Alarm on DLQ depth + 5xx rate.

### 16.6 Stripe Tax origin mistakes

- **Risk:** Wrong origin = wrong tax filed = legal/financial exposure.
- **Mitigation:** Stripe Tax origin set once at infra bootstrap, captured in IaC, change requires SRE + finance sign-off. Audited quarterly.

### 16.7 Promotional grant abuse

- **Risk:** Admin grants unlimited credits / Pro tier in error. No revert workflow yet.
- **Mitigation:** Admin actions audit-logged; admin console (§016) needs a "revoke grant" button (T-021). Add monetary impact threshold for grants — over $X needs super-admin approval.

### 16.8 Schema migrations on live billing data

- **Risk:** Live billing data is money. Migrations that lock tables = downtime = lost charges.
- **Mitigation:** All `billing.*` migrations follow expand-contract pattern with backfill; no `ALTER TABLE ... DEFAULT` on `Subscription` or `CreditTransaction`; PR checklist enforced.

### 16.9 Apple Family Sharing entitlement leak

- **Risk:** One Family Sharing purchase grants Premium to 6 users. We could over-charge our infra cost (AI credits are real money).
- **Mitigation:** RC reports family-shared entitlements separately. We mark `EntitlementSnapshot.source = 'family_share'`. AI credit grants are scoped to the **purchaser only**, not to family members. UI explicitly says "Family Sharing grants Premium features but credits stay with the purchaser." Confirmed against Apple policy at Phase 5b.

### 16.10 Tax-code misclassification

- **Risk:** Wrong Stripe Tax code on credit bundles = wrong tax rate = back-filing required.
- **Mitigation:** Phase 5b finance review of tax codes before P12 ship. Manual periodic audit of invoice tax lines per region.

---

## 17. Phase 5b reconciliation hooks

- Confirm exact Stripe Tax product codes with Stripe support.
- Finalize India OIDAR vs Paddle decision; either resolves T-023 to Stripe-only or pulls Paddle integration into scope.
- Lock RevenueCat offering + product matrix once App Store + Play Console SKUs are minted.
- Finalize numeric values in `EntitlementConfig` seed migration with product (placeholders in §3 are not launch values).
- Reconcile with §008 on the moderation-pause-on-ban precise semantics (credit back, vs grant equivalent free days, vs leave it).
- Reconcile with §012 on exact credit cost per `/mockup-image`, `/mockup-audio`, etc. (currently placeholders).

---

## 18. Done definition

This phase is done when:

1. All AC-1..AC-16 verifications pass in CI on every PR.
2. Stripe + RC live keys are in Secrets Manager and validated via smoke test.
3. Webhook handlers have run for ≥7 days against Stripe live + RC live with zero unprocessed-after-retry events.
4. Reconciliation jobs report zero drift for ≥3 consecutive nights.
5. Admin can change a tier value and watch it propagate live.
6. India GST path decided + implemented (or India web purchases gated behind feature flag pending decision).
7. Runbook for refund-stuck cases, dunning-stuck cases, and webhook-replay procedures is checked into ops repo.
