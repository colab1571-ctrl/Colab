#!/usr/bin/env bash
# sync-products.sh — RevenueCat REST API product configuration sync
#
# Configures Offerings, Packages, and Entitlements in RevenueCat via the
# RevenueCat v1 REST API. Prices are NOT set here — prices must be configured
# in App Store Connect and Google Play Console directly.
#
# PREREQUISITES:
#   - RC_API_KEY: RevenueCat secret API key (from RevenueCat Dashboard → API Keys)
#   - RC_PROJECT_ID: RevenueCat project ID (from Dashboard URL)
#   - App Store products must already be created in App Store Connect
#   - Google Play products must already be created in Play Console
#
# USAGE:
#   RC_API_KEY=sk_... RC_PROJECT_ID=proj_... ./scripts/revenuecat/sync-products.sh
#
# NOTE: RevenueCat's REST API v1 covers entitlement creation and offering
#       configuration. Product metadata (prices, descriptions) is managed
#       in the store dashboards directly. This script is a placeholder that
#       must be validated against the live RevenueCat API before production use.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RC_BASE_URL="https://api.revenuecat.com/v1"
RC_API_KEY="${RC_API_KEY:?RC_API_KEY must be set}"
RC_PROJECT_ID="${RC_PROJECT_ID:?RC_PROJECT_ID must be set}"
APP_ID_IOS="${RC_APP_ID_IOS:-}" # RevenueCat app ID for iOS app
APP_ID_ANDROID="${RC_APP_ID_ANDROID:-}" # RevenueCat app ID for Android app

RC_HEADERS=(
  -H "Authorization: Bearer ${RC_API_KEY}"
  -H "Content-Type: application/json"
  -H "X-Platform: app"
)

# ---------------------------------------------------------------------------
# Helper: make API call with error handling
# ---------------------------------------------------------------------------
rc_api() {
  local method="${1}"
  local path="${2}"
  local body="${3:-}"
  local response

  if [[ -n "${body}" ]]; then
    response=$(curl -sf -X "${method}" "${RC_BASE_URL}${path}" \
      "${RC_HEADERS[@]}" \
      -d "${body}" 2>&1) || {
      echo "[rc-sync] ERROR: ${method} ${path} failed"
      echo "[rc-sync] Response: ${response}"
      return 1
    }
  else
    response=$(curl -sf -X "${method}" "${RC_BASE_URL}${path}" \
      "${RC_HEADERS[@]}" 2>&1) || {
      echo "[rc-sync] ERROR: ${method} ${path} failed"
      echo "[rc-sync] Response: ${response}"
      return 1
    }
  fi

  echo "${response}"
}

# ---------------------------------------------------------------------------
# Step 1: Create / verify entitlements
# ---------------------------------------------------------------------------
create_entitlements() {
  echo "[rc-sync] Creating entitlements..."

  local entitlements=(
    '{"lookup_key": "premium", "display_name": "Premium"}'
    '{"lookup_key": "premium_pro", "display_name": "Premium Pro"}'
    '{"lookup_key": "ai_credits", "display_name": "AI Credits"}'
  )

  for entitlement_body in "${entitlements[@]}"; do
    local lookup_key
    lookup_key=$(echo "${entitlement_body}" | grep -o '"lookup_key": "[^"]*"' | cut -d'"' -f4)
    echo "[rc-sync] Creating entitlement: ${lookup_key}"
    rc_api POST "/projects/${RC_PROJECT_ID}/entitlements" "${entitlement_body}" || \
      echo "[rc-sync] Entitlement ${lookup_key} may already exist — continuing"
  done
}

# ---------------------------------------------------------------------------
# Step 2: Create / verify products
# ---------------------------------------------------------------------------
create_products() {
  echo "[rc-sync] Syncing products..."

  # Each product maps to store_identifier (App Store product ID or Play product ID)
  # Type: subscription | non_consumable | consumable
  local ios_products=(
    '{"store_identifier": "premium_monthly", "type": "subscription"}'
    '{"store_identifier": "premium_annual", "type": "subscription"}'
    '{"store_identifier": "premium_pro_monthly", "type": "subscription"}'
    '{"store_identifier": "premium_pro_annual", "type": "subscription"}'
    '{"store_identifier": "ai_credits_100", "type": "consumable"}'
    '{"store_identifier": "ai_credits_500", "type": "consumable"}'
    '{"store_identifier": "ai_credits_1000", "type": "consumable"}'
  )

  if [[ -n "${APP_ID_IOS}" ]]; then
    for product_body in "${ios_products[@]}"; do
      local store_id
      store_id=$(echo "${product_body}" | grep -o '"store_identifier": "[^"]*"' | cut -d'"' -f4)
      echo "[rc-sync] Creating iOS product: ${store_id}"
      rc_api POST "/apps/${APP_ID_IOS}/products" "${product_body}" || \
        echo "[rc-sync] Product ${store_id} may already exist — continuing"
    done
  else
    echo "[rc-sync] RC_APP_ID_IOS not set — skipping iOS product creation"
  fi

  if [[ -n "${APP_ID_ANDROID}" ]]; then
    for product_body in "${ios_products[@]}"; do
      local store_id
      store_id=$(echo "${product_body}" | grep -o '"store_identifier": "[^"]*"' | cut -d'"' -f4)
      echo "[rc-sync] Creating Android product: ${store_id}"
      rc_api POST "/apps/${APP_ID_ANDROID}/products" "${product_body}" || \
        echo "[rc-sync] Product ${store_id} may already exist — continuing"
    done
  else
    echo "[rc-sync] RC_APP_ID_ANDROID not set — skipping Android product creation"
  fi
}

# ---------------------------------------------------------------------------
# Step 3: Create default Offering + Packages
# ---------------------------------------------------------------------------
create_offering() {
  echo "[rc-sync] Creating default Offering..."

  local offering_body
  offering_body=$(cat << 'EOF'
{
  "lookup_key": "default",
  "display_name": "Default Offering",
  "packages": [
    {
      "lookup_key": "$monthly",
      "display_name": "Monthly",
      "duration": "P1M",
      "product_identifier": "premium_monthly"
    },
    {
      "lookup_key": "$annual",
      "display_name": "Annual",
      "duration": "P1Y",
      "product_identifier": "premium_annual"
    },
    {
      "lookup_key": "pro_monthly",
      "display_name": "Pro Monthly",
      "duration": "P1M",
      "product_identifier": "premium_pro_monthly"
    },
    {
      "lookup_key": "pro_annual",
      "display_name": "Pro Annual",
      "duration": "P1Y",
      "product_identifier": "premium_pro_annual"
    },
    {
      "lookup_key": "credits_small",
      "display_name": "100 AI Credits",
      "product_identifier": "ai_credits_100"
    },
    {
      "lookup_key": "credits_medium",
      "display_name": "500 AI Credits",
      "product_identifier": "ai_credits_500"
    },
    {
      "lookup_key": "credits_large",
      "display_name": "1000 AI Credits",
      "product_identifier": "ai_credits_1000"
    }
  ]
}
EOF
)

  rc_api POST "/projects/${RC_PROJECT_ID}/offerings" "${offering_body}" || \
    echo "[rc-sync] Default offering may already exist — continuing"
}

# ---------------------------------------------------------------------------
# Step 4: Print summary
# ---------------------------------------------------------------------------
print_summary() {
  echo ""
  echo "[rc-sync] ============================================"
  echo "[rc-sync] RevenueCat product sync complete."
  echo "[rc-sync] ============================================"
  echo ""
  echo "NEXT STEPS (manual — cannot be done via API):"
  echo "  1. Set prices for each product in App Store Connect + Play Console"
  echo "  2. Submit subscription products for Apple review (independent of app)"
  echo "  3. Activate products in Play Console (status must be 'Active')"
  echo "  4. Configure RevenueCat Webhook in dashboard:"
  echo "     URL: https://api.[brandname].com/billing/webhooks/revenuecat"
  echo "  5. Copy webhook HMAC secret → AWS Secrets Manager:"
  echo "     colab/prod/revenuecat/webhook-hmac"
  echo "  6. Run sandbox purchase flow on TestFlight + Play Alpha builds"
  echo ""
  echo "VERIFY in RevenueCat Dashboard:"
  echo "  - Project → Entitlements: premium, premium_pro, ai_credits"
  echo "  - Project → Products: 7 products for iOS + 7 for Android"
  echo "  - Project → Offerings: 'default' with 7 packages"
  echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "[rc-sync] Starting RevenueCat product sync..."
echo "[rc-sync] Project: ${RC_PROJECT_ID}"
echo ""

create_entitlements
create_products
create_offering
print_summary
