#!/usr/bin/env bash
# scripts/deploy/migrate-supabase.sh
# Run Alembic migrations for all Stage 3 services against Supabase.
#
# Usage:
#   export SUPABASE_DB_URL="postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres"
#   bash scripts/deploy/migrate-supabase.sh
#
# Prerequisites:
#   - uv (Python package manager) installed: curl -LsSf https://astral.sh/uv/install.sh | sh
#   - SUPABASE_DB_URL environment variable set

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
  echo "ERROR: SUPABASE_DB_URL is not set."
  echo "  export SUPABASE_DB_URL='postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres'"
  exit 1
fi

echo "→ Using DB: ${SUPABASE_DB_URL//:*@/:***@}"  # mask password in logs

# ── Apply base schema SQL ─────────────────────────────────────────────────────
echo ""
echo "== Applying base schema SQL (01-schemas.sql) =="
if [[ -f "$REPO_ROOT/scripts/db-init/01-schemas.sql" ]]; then
  psql "$SUPABASE_DB_URL" -f "$REPO_ROOT/scripts/db-init/01-schemas.sql"
  echo "   ✓ Base schemas applied."
else
  echo "   WARN: scripts/db-init/01-schemas.sql not found — skipping."
fi

# ── Run Alembic migrations ────────────────────────────────────────────────────
run_migration() {
  local svc="$1"
  local svc_dir="$REPO_ROOT/services/$svc"

  echo ""
  echo "== Migrating $svc =="

  if [[ ! -f "$svc_dir/alembic.ini" ]]; then
    echo "   WARN: No alembic.ini found for $svc — skipping."
    return
  fi

  (
    cd "$svc_dir"
    DATABASE_URL="$SUPABASE_DB_URL" \
      uv run --package "$svc" \
      alembic upgrade head
  )

  echo "   ✓ $svc migrations complete."
}

run_migration "auth-svc"
run_migration "profile-svc"
run_migration "gateway-svc"

echo ""
echo "== All Stage 3 migrations complete =="
