# RevenueCat IAP Product Configuration

**Version**: 1.0  
**Date**: 2026-05-11  
**Reference**: Phase 019 plan §7

Prices are placeholders — fill real values in RevenueCat dashboard and App Store Connect / Play Console before launch. Do not hardcode prices anywhere in app code; fetch from RevenueCat `Offerings` API.

---

## 1. Product Definitions

### Subscriptions

| Product ID | Display name | Type | Platform | Tier | Interval | Price placeholder |
|------------|-------------|------|----------|------|----------|------------------|
| `premium_monthly` | Premium Monthly | Auto-renewable subscription | iOS + Android | Premium | 1 month | $X.99/mo |
| `premium_annual` | Premium Annual | Auto-renewable subscription | iOS + Android | Premium | 1 year | $XX.99/yr |
| `premium_pro_monthly` | Pro Monthly | Auto-renewable subscription | iOS + Android | Premium Pro | 1 month | $XX.99/mo |
| `premium_pro_annual` | Pro Annual | Auto-renewable subscription | iOS + Android | Premium Pro | 1 year | $XXX.99/yr |

### Consumables (AI Credits)

| Product ID | Display name | Type | Platform | Credits granted | Price placeholder |
|------------|-------------|------|----------|----------------|-----------------|
| `ai_credits_100` | 100 AI Credits | Consumable | iOS + Android | 100 | $X.99 |
| `ai_credits_500` | 500 AI Credits | Consumable | iOS + Android | 500 | $X.99 |
| `ai_credits_1000` | 1,000 AI Credits | Consumable | iOS + Android | 1,000 | $XX.99 |

---

## 2. RevenueCat Entitlements Mapping

| Entitlement ID | Description | Products that unlock it |
|----------------|-------------|------------------------|
| `premium` | Premium tier: unlimited matching, workspace creation, priority feed, 50 AI credits/month | `premium_monthly`, `premium_annual`, `premium_pro_monthly`, `premium_pro_annual` |
| `premium_pro` | Pro tier: all Premium + AI image generation, unlimited AI credits, advanced collaboration tools | `premium_pro_monthly`, `premium_pro_annual` |
| `ai_credits` | Add-on credit wallet top-up (consumable) | `ai_credits_100`, `ai_credits_500`, `ai_credits_1000` |

---

## 3. RevenueCat Offerings

### Offering: `default`

Configure as the default Offering in RevenueCat dashboard. Packages:

| Package identifier | Products | Display |
|-------------------|---------|---------|
| `$monthly` | `premium_monthly` | Monthly subscription |
| `$annual` | `premium_annual` | Annual subscription (best value) |
| `pro_monthly` | `premium_pro_monthly` | Pro monthly |
| `pro_annual` | `premium_pro_annual` | Pro annual |
| `credits_small` | `ai_credits_100` | 100 AI credits |
| `credits_medium` | `ai_credits_500` | 500 AI credits |
| `credits_large` | `ai_credits_1000` | 1,000 AI credits |

---

## 4. Tier Feature Matrix

| Feature | Free | Premium | Pro |
|---------|------|---------|-----|
| Discovery feed | 10 profiles/day | Unlimited | Unlimited |
| Vibe Checks sent | 3/month | Unlimited | Unlimited |
| Active collaborations | 1 | 5 | Unlimited |
| AI chat commands | None | `/brainstorm`, `/summarize-chat` | All commands |
| AI image generation (`/mockup-image`) | None | None | Yes (consumes credits) |
| Monthly AI credits included | 0 | 50 | Unlimited |
| Portfolio items | 5 | 50 | Unlimited |
| File sharing per collab | 100 MB | 5 GB | 50 GB |
| Export (CSV, PDF) | No | Yes | Yes |
| Verified Profile Badge | KYC required (any tier) | KYC required | KYC required |

*All values above are admin-configurable via admin-svc `EntitlementConfig` entity; these are defaults.*

---

## 5. RevenueCat SDK Integration

### Mobile (React Native)

```typescript
// apps/mobile/src/lib/revenuecat.ts
import Purchases, { PurchasesPackage } from 'react-native-purchases';

export async function initRevenueCat() {
  Purchases.configure({
    apiKey: Platform.select({
      ios: process.env.EXPO_PUBLIC_RC_API_KEY_IOS!,
      android: process.env.EXPO_PUBLIC_RC_API_KEY_ANDROID!,
    })!,
  });
}

export async function getOfferings() {
  const offerings = await Purchases.getOfferings();
  return offerings.current;
}

export async function purchasePackage(pkg: PurchasesPackage) {
  const { customerInfo } = await Purchases.purchasePackage(pkg);
  return customerInfo;
}
```

### Webhook → billing-svc

RevenueCat sends all purchase events to `POST /billing/webhooks/revenuecat`.

In RevenueCat dashboard → Project Settings → Integrations → Webhooks:
- URL: `https://api.[brandname].com/billing/webhooks/revenuecat`
- Version: V2
- Copy HMAC secret → store in AWS Secrets Manager: `colab/prod/revenuecat/webhook-hmac`

---

## 6. App Store Connect Product Setup

For each subscription product in App Store Connect:

1. Go to App Store Connect → My Apps → [App] → In-App Purchases
2. Create "Auto-Renewable Subscription"
3. Product ID: exactly matches the Product ID column above
4. Reference name: human-readable for internal tracking
5. Subscription group: `Colab Premium` (create new group for first product)
6. Duration: match Interval column
7. Price tier: set in "Pricing" tab (do not set prices from `scripts/revenuecat/sync-products.sh` — use dashboard)
8. Subscription group level: Premium = level 1, Pro = level 2 (higher level = higher tier)
9. Localization: add en-US display name and description
10. Submit for review (can be reviewed independently of app)

---

## 7. Google Play Console Product Setup

For each subscription product in Play Console:

1. Go to Play Console → [App] → Monetize → Products → Subscriptions
2. Create new subscription
3. Product ID: exactly matches Product ID column above
4. Name + description in en-US
5. Base plan: set billing period and price
6. Grace period: 3 days
7. Account hold: 30 days
8. Activate the subscription (must be Active before RevenueCat can sync)

For consumables (AI credits):
1. Go to In-app products (not Subscriptions)
2. Create managed product
3. Product ID as above
4. Set price
5. Activate

---

## 8. Sync Checklist (T-022)

- [ ] All 4 subscription products created in App Store Connect (`Submitted` status)
- [ ] All 3 consumable products created in App Store Connect (`Submitted` status)
- [ ] All 4 subscription products created in Play Console (`Active` status)
- [ ] All 3 consumable products created in Play Console (`Active` status)
- [ ] RevenueCat project connected to App Store Connect via Shared Secret
- [ ] RevenueCat project connected to Google Play via Google Service Account JSON
- [ ] Webhook URL configured in RevenueCat → billing-svc
- [ ] Webhook HMAC secret in AWS Secrets Manager
- [ ] Default Offering configured with all 7 packages
- [ ] Sandbox test: purchase `premium_monthly` on iOS simulator
- [ ] Sandbox test: restore purchase on second test device
- [ ] Sandbox test: cancel subscription; verify entitlement removed after grace period
- [ ] Sandbox test: `ai_credits_100` consumable; verify 100 credits added to wallet
- [ ] Sandbox test: duplicate webhook delivery; verify no double-credit
- [ ] Stripe web products created (matching SKU names for cross-platform price parity per FR-E-3)
