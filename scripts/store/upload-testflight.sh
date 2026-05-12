#!/usr/bin/env bash
# upload-testflight.sh — Fastlane wrapper for TestFlight upload
#
# Builds a production iOS IPA via EAS and uploads to TestFlight.
# Screenshots and metadata upload is handled separately via Fastlane deliver.
#
# PREREQUISITES:
#   - fastlane installed: gem install fastlane
#   - EAS CLI installed: npm install -g eas-cli
#   - EXPO_TOKEN set in environment (or CI secrets)
#   - APP_STORE_CONNECT_API_KEY_ID, APP_STORE_CONNECT_API_KEY_ISSUER_ID,
#     APP_STORE_CONNECT_API_KEY_CONTENT (base64-encoded .p8 file) set
#   - Apple Developer account enrolled; bundle ID registered
#
# USAGE:
#   # Full build + upload:
#   ./scripts/store/upload-testflight.sh
#
#   # Upload pre-built IPA:
#   ./scripts/store/upload-testflight.sh --ipa path/to/build.ipa
#
# NOTE: This is a skeleton. EAS build + Fastlane upload flow must be
#       validated against live Apple Developer credentials before first run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IPA_PATH="${1:-}"
FASTLANE_DIR="${REPO_ROOT}/apps/mobile/fastlane"

# ---------------------------------------------------------------------------
# Validate prerequisites
# ---------------------------------------------------------------------------
check_prereqs() {
  local missing=0

  command -v fastlane >/dev/null 2>&1 || { echo "[ERROR] fastlane not found. Install: gem install fastlane"; missing=1; }
  command -v eas >/dev/null 2>&1      || { echo "[ERROR] eas-cli not found. Install: npm install -g eas-cli"; missing=1; }

  [[ -n "${EXPO_TOKEN:-}" ]]                              || { echo "[ERROR] EXPO_TOKEN not set"; missing=1; }
  [[ -n "${APP_STORE_CONNECT_API_KEY_ID:-}" ]]            || { echo "[ERROR] APP_STORE_CONNECT_API_KEY_ID not set"; missing=1; }
  [[ -n "${APP_STORE_CONNECT_API_KEY_ISSUER_ID:-}" ]]     || { echo "[ERROR] APP_STORE_CONNECT_API_KEY_ISSUER_ID not set"; missing=1; }
  [[ -n "${APP_STORE_CONNECT_API_KEY_CONTENT:-}" ]]       || { echo "[ERROR] APP_STORE_CONNECT_API_KEY_CONTENT not set (base64 .p8)"; missing=1; }

  if [[ "${missing}" -gt 0 ]]; then
    echo "[upload-testflight] Prerequisites not met. Exiting."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Write ASC API key to temp file (Fastlane expects a .p8 file)
# ---------------------------------------------------------------------------
setup_asc_key() {
  ASC_KEY_PATH="/tmp/asc_api_key.p8"
  echo "${APP_STORE_CONNECT_API_KEY_CONTENT}" | base64 --decode > "${ASC_KEY_PATH}"
  chmod 600 "${ASC_KEY_PATH}"
  echo "[upload-testflight] ASC API key written to ${ASC_KEY_PATH}"
}

# ---------------------------------------------------------------------------
# Build IPA via EAS (if not provided)
# ---------------------------------------------------------------------------
build_ipa() {
  if [[ -n "${IPA_PATH}" && -f "${IPA_PATH}" ]]; then
    echo "[upload-testflight] Using pre-built IPA: ${IPA_PATH}"
    return
  fi

  echo "[upload-testflight] Building production IPA via EAS..."
  cd "${REPO_ROOT}/apps/mobile"

  eas build \
    --platform ios \
    --profile production \
    --non-interactive \
    --json \
    --output "${REPO_ROOT}/build/colab-ios-production.ipa" \
    2>&1 | tee /tmp/eas-build.log

  IPA_PATH="${REPO_ROOT}/build/colab-ios-production.ipa"
  echo "[upload-testflight] Build complete: ${IPA_PATH}"
}

# ---------------------------------------------------------------------------
# Upload to TestFlight via Fastlane pilot
# ---------------------------------------------------------------------------
upload_to_testflight() {
  echo "[upload-testflight] Uploading to TestFlight..."

  # Create minimal Fastfile if not present
  mkdir -p "${FASTLANE_DIR}"
  if [[ ! -f "${FASTLANE_DIR}/Fastfile" ]]; then
    cat > "${FASTLANE_DIR}/Fastfile" << 'FASTFILE'
default_platform(:ios)

platform :ios do
  desc "Upload to TestFlight"
  lane :beta do
    pilot(
      skip_submission: false,
      skip_waiting_for_build_processing: false,
      notify_external_testers: false,
      changelog: ENV["TESTFLIGHT_CHANGELOG"] || "Internal beta build",
    )
  end
end
FASTFILE
  fi

  # Create Appfile if not present
  if [[ ! -f "${FASTLANE_DIR}/Appfile" ]]; then
    cat > "${FASTLANE_DIR}/Appfile" << APPFILE
app_identifier("${BUNDLE_ID:-com.colab.app}")
apple_id("${APPLE_ID:-noreply@colab.test}")
APPFILE
  fi

  cd "${FASTLANE_DIR}/.."

  fastlane pilot upload \
    --ipa "${IPA_PATH}" \
    --api_key_path "${ASC_KEY_PATH}" \
    --skip_waiting_for_build_processing false \
    --changelog "${TESTFLIGHT_CHANGELOG:-Beta build $(date +%Y-%m-%d)}" \
    --notify_external_testers false

  echo "[upload-testflight] Upload complete. Build will appear in TestFlight after processing (~10–30 min)."
}

# ---------------------------------------------------------------------------
# Upload metadata + screenshots (optional, on explicit flag)
# ---------------------------------------------------------------------------
upload_metadata() {
  if [[ "${UPLOAD_METADATA:-false}" != "true" ]]; then
    echo "[upload-testflight] Skipping metadata upload (UPLOAD_METADATA != true)"
    return
  fi

  echo "[upload-testflight] Uploading App Store metadata + screenshots..."
  cd "${FASTLANE_DIR}/.."

  fastlane deliver \
    --api_key_path "${ASC_KEY_PATH}" \
    --metadata_path "${REPO_ROOT}/fastlane/metadata" \
    --screenshots_path "${REPO_ROOT}/screenshots/ios" \
    --skip_binary_upload true \
    --force true

  echo "[upload-testflight] Metadata upload complete."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
check_prereqs
setup_asc_key

case "${1:-}" in
  --ipa)
    IPA_PATH="${2:?Usage: $0 --ipa path/to/build.ipa}"
    ;;
  --metadata-only)
    ASC_KEY_PATH="/tmp/asc_api_key.p8"
    UPLOAD_METADATA=true
    upload_metadata
    exit 0
    ;;
esac

build_ipa
upload_to_testflight
upload_metadata

echo "[upload-testflight] Done."
