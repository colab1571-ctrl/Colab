#!/usr/bin/env bash
# =============================================================================
# Colab Stage-2 Demo Seed Script
# Seeds: test user + sample profiles via auth-svc and profile-svc directly
# =============================================================================
set -euo pipefail

AUTH="http://localhost:8001"
PROFILE="http://localhost:8002"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${YELLOW}[SEED]${NC} $1"; }
pass() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${RED}[WARN]${NC} $1"; }

# ---------------------------------------------------------------------------
# 1. Create seed user
# ---------------------------------------------------------------------------
info "Creating seed user: demo@colab.test"
SIGNUP=$(curl -s -w '\n%{http_code}' \
  -X POST "${AUTH}/auth/signup/email" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@colab.test",
    "password": "DemoPass123!",
    "age_attestation": true,
    "accept_tos": true,
    "accept_privacy": true,
    "accept_community": true,
    "tos_version": "1.0",
    "privacy_version": "1.0",
    "community_version": "1.0"
  }')

BODY=$(echo "$SIGNUP" | head -1)
STATUS=$(echo "$SIGNUP" | tail -1)

if [ "$STATUS" = "201" ]; then
  ACCESS_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['access_token'])" 2>/dev/null || echo "")
  pass "Seed user created (status: ${STATUS})"
elif [ "$STATUS" = "409" ]; then
  # User already exists — log in instead
  info "Seed user already exists; logging in..."
  LOGIN=$(curl -s -w '\n%{http_code}' \
    -X POST "${AUTH}/auth/login/email" \
    -H "Content-Type: application/json" \
    -d '{"email": "demo@colab.test", "password": "DemoPass123!"}')
  BODY=$(echo "$LOGIN" | head -1)
  STATUS=$(echo "$LOGIN" | tail -1)
  ACCESS_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['access_token'])" 2>/dev/null || echo "")
  pass "Seed user login (status: ${STATUS})"
else
  warn "Seed user creation failed (status: ${STATUS}): ${BODY}"
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Create/update profile for seed user
# ---------------------------------------------------------------------------
info "Creating profile for seed user..."
PROFILE_RESP=$(curl -s -w '\n%{http_code}' \
  -X POST "${PROFILE}/api/v1/profile/me" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Demo User",
    "bio": "Stage-2 demo seed profile",
    "handle": "demouser"
  }')

P_STATUS=$(echo "$PROFILE_RESP" | tail -1)
if [ "$P_STATUS" = "201" ] || [ "$P_STATUS" = "200" ] || [ "$P_STATUS" = "409" ]; then
  pass "Profile seed complete (status: ${P_STATUS})"
else
  warn "Profile create returned ${P_STATUS} — check profile-svc logs"
fi

echo ""
pass "Seed complete. Login: demo@colab.test / DemoPass123!"
