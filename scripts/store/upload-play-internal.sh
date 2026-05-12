#!/usr/bin/env bash
# upload-play-internal.sh — Fastlane wrapper for Google Play upload
#
# Builds a production Android AAB via EAS and uploads to Play Console
# internal testing track.
#
# PREREQUISITES:
#   - fastlane installed: gem install fastlane
#   - EAS CLI installed: npm install -g eas-cli
#   - EXPO_TOKEN set in environment
#   - GOOGLE_PLAY_SERVICE_ACCOUNT_JSON (path to service account JSON file)
#     OR GOOGLE_PLAY_JSON_KEY_DATA (JSON content as env var)
#   - Google Play developer account enrolled; app created in Play Console
#
# USAGE:
#   # Full build + upload:
#   ./scripts/store/upload-play-internal.sh
#
#   # Upload pre-built AAB:
#   ./scripts/store/upload-play-internal.sh --aab path/to/build.aab
#
#   # Upload to alpha track (closed beta):
#   PLAY_TRACK=alpha ./scripts/store/upload-play-internal.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
AAB_PATH="${1:-}"
PLAY_TRACK="${PLAY_TRACK:-internal}"
FASTLANE_DIR="${REPO_ROOT}/apps/mobile/fastlane"

# ---------------------------------------------------------------------------
# Validate prerequisites
# ---------------------------------------------------------------------------
check_prereqs() {
  local missing=0

  command -v fastlane >/dev/null 2>&1 || { echo "[ERROR] fastlane not found. Install: gem install fastlane"; missing=1; }
  command -v eas >/dev/null 2>&1      || { echo "[ERROR] eas-cli not found. Install: npm install -g eas-cli"; missing=1; }

  [[ -n "${EXPO_TOKEN:-}" ]] || { echo "[ERROR] EXPO_TOKEN not set"; missing=1; }

  # Accept either a file path or JSON content
  if [[ -z "${GOOGLE_PLAY_SERVICE_ACCOUNT_JSON:-}" && -z "${GOOGLE_PLAY_JSON_KEY_DATA:-}" ]]; then
    echo "[ERROR] Set GOOGLE_PLAY_SERVICE_ACCOUNT_JSON (file path) or GOOGLE_PLAY_JSON_KEY_DATA (JSON content)"
    missing=1
  fi

  if [[ "${missing}" -gt 0 ]]; then
    echo "[upload-play] Prerequisites not met. Exiting."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Resolve service account JSON path
# ---------------------------------------------------------------------------
setup_service_account() {
  if [[ -n "${GOOGLE_PLAY_JSON_KEY_DATA:-}" ]]; then
    JSON_KEY_PATH="/tmp/play_service_account.json"
    echo "${GOOGLE_PLAY_JSON_KEY_DATA}" > "${JSON_KEY_PATH}"
    chmod 600 "${JSON_KEY_PATH}"
  else
    JSON_KEY_PATH="${GOOGLE_PLAY_SERVICE_ACCOUNT_JSON}"
    if [[ ! -f "${JSON_KEY_PATH}" ]]; then
      echo "[ERROR] Service account JSON file not found: ${JSON_KEY_PATH}"
      exit 1
    fi
  fi
  echo "[upload-play] Using service account: ${JSON_KEY_PATH}"
}

# ---------------------------------------------------------------------------
# Build AAB via EAS
# ---------------------------------------------------------------------------
build_aab() {
  if [[ -n "${AAB_PATH}" && -f "${AAB_PATH}" ]]; then
    echo "[upload-play] Using pre-built AAB: ${AAB_PATH}"
    return
  fi

  echo "[upload-play] Building production AAB via EAS..."
  cd "${REPO_ROOT}/apps/mobile"

  eas build \
    --platform android \
    --profile production \
    --non-interactive \
    --json \
    2>&1 | tee /tmp/eas-android-build.log

  # Download the AAB from EAS after build
  BUILD_URL=$(grep '"artifacts"' /tmp/eas-android-build.log | grep -o 'https://[^"]*\.aab' | head -1)
  mkdir -p "${REPO_ROOT}/build"
  AAB_PATH="${REPO_ROOT}/build/colab-android-production.aab"

  if [[ -n "${BUILD_URL}" ]]; then
    curl -L -o "${AAB_PATH}" "${BUILD_URL}"
    echo "[upload-play] Downloaded AAB: ${AAB_PATH}"
  else
    echo "[ERROR] Could not locate AAB download URL in EAS output. Check /tmp/eas-android-build.log"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Upload to Play Console via Fastlane supply
# ---------------------------------------------------------------------------
upload_to_play() {
  echo "[upload-play] Uploading AAB to Play Console track: ${PLAY_TRACK}..."

  mkdir -p "${FASTLANE_DIR}"
  if [[ ! -f "${FASTLANE_DIR}/Fastfile" ]]; then
    cat > "${FASTLANE_DIR}/Fastfile" << 'FASTFILE'
default_platform(:android)

platform :android do
  desc "Upload to Play Console"
  lane :deploy do
    upload_to_play_store(
      track: ENV["PLAY_TRACK"] || "internal",
      release_status: "draft",
      skip_upload_screenshots: false,
      skip_upload_metadata: false,
    )
  end
end
FASTFILE
  fi

  # Appfile for Android
  if [[ ! -f "${FASTLANE_DIR}/Appfile" ]]; then
    cat > "${FASTLANE_DIR}/Appfile" << APPFILE
json_key_file("${JSON_KEY_PATH}")
package_name("${PACKAGE_NAME:-com.colab.app}")
APPFILE
  fi

  cd "${FASTLANE_DIR}/.."

  fastlane supply \
    --aab "${AAB_PATH}" \
    --track "${PLAY_TRACK}" \
    --release_status "draft" \
    --json_key "${JSON_KEY_PATH}" \
    --package_name "${PACKAGE_NAME:-com.colab.app}" \
    --skip_upload_screenshots "${SKIP_SCREENSHOTS:-true}" \
    --skip_upload_metadata "${SKIP_METADATA:-true}"

  echo "[upload-play] Upload complete."
  echo "[upload-play] Track '${PLAY_TRACK}' — go to Play Console to review and publish."
}

# ---------------------------------------------------------------------------
# Upload metadata + screenshots (optional)
# ---------------------------------------------------------------------------
upload_metadata() {
  if [[ "${UPLOAD_METADATA:-false}" != "true" ]]; then
    echo "[upload-play] Skipping metadata upload (UPLOAD_METADATA != true)"
    return
  fi

  echo "[upload-play] Uploading Play Store metadata + screenshots..."
  cd "${FASTLANE_DIR}/.."

  fastlane supply \
    --json_key "${JSON_KEY_PATH}" \
    --package_name "${PACKAGE_NAME:-com.colab.app}" \
    --metadata_path "${REPO_ROOT}/fastlane/android/metadata" \
    --screenshots_path "${REPO_ROOT}/screenshots/android" \
    --skip_upload_apk true \
    --skip_upload_aab true

  echo "[upload-play] Metadata upload complete."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
check_prereqs
setup_service_account

case "${1:-}" in
  --aab)
    AAB_PATH="${2:?Usage: $0 --aab path/to/build.aab}"
    ;;
  --metadata-only)
    UPLOAD_METADATA=true
    upload_metadata
    exit 0
    ;;
esac

build_aab
upload_to_play
upload_metadata

echo "[upload-play] Done. Review the release in Play Console before promoting."
