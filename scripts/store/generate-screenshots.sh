#!/usr/bin/env bash
# generate-screenshots.sh — Detox-based screenshot capture pipeline
#
# Captures App Store / Google Play screenshots using Detox e2e tests.
# Produces screenshots at required resolutions for all device classes.
#
# PREREQUISITES (must be set up before running):
#   - Xcode 16+ with iOS Simulator (for iOS screenshots)
#   - Android SDK + emulator AVDs (for Android screenshots)
#   - Detox CLI: npm install -g detox-cli
#   - App built in release mode: eas build --profile staging --platform ios
#   - .env.screenshot with SCREENSHOT_USER_EMAIL and SCREENSHOT_USER_PASSWORD
#     (pre-seeded test account with completed onboarding + seed data)
#
# USAGE:
#   ./scripts/store/generate-screenshots.sh [ios|android|all]
#
# OUTPUT:
#   screenshots/ios/   — PNG files per device class and screen
#   screenshots/android/ — PNG files per device class and screen

set -euo pipefail

PLATFORM="${1:-all}"
SCREENSHOT_DIR="$(pwd)/screenshots"
IOS_DIR="${SCREENSHOT_DIR}/ios"
ANDROID_DIR="${SCREENSHOT_DIR}/android"

# ---------------------------------------------------------------------------
# Device configurations
# ---------------------------------------------------------------------------

# iOS simulators — names must match installed simulators in Xcode
IOS_SIMULATORS=(
  "iPhone 16 Pro Max"     # 6.9" — required
  "iPad Pro 13-inch (M4)" # 13" — required
)

# Android AVDs — must be created via Android Studio or avdmanager
ANDROID_AVDS=(
  "Pixel_9_Pro_API_35"     # phone portrait
  "Nexus_10_API_35"        # 10-inch tablet
)

# ---------------------------------------------------------------------------
# Screens to capture (maps to Detox test IDs)
# ---------------------------------------------------------------------------
SCREENS=(
  "discovery_feed"
  "swipe_card_match_score"
  "vibe_check_send"
  "collab_workspace_chat"
  "ai_command_brainstorm"
  "profile_verified_badge"
)

# ---------------------------------------------------------------------------
# iOS screenshot capture
# ---------------------------------------------------------------------------
capture_ios() {
  echo "[screenshots] Starting iOS capture..."
  mkdir -p "${IOS_DIR}"

  for SIMULATOR in "${IOS_SIMULATORS[@]}"; do
    SAFE_NAME="${SIMULATOR// /_}"
    mkdir -p "${IOS_DIR}/${SAFE_NAME}"

    echo "[screenshots] Booting simulator: ${SIMULATOR}"
    xcrun simctl boot "${SIMULATOR}" 2>/dev/null || true
    sleep 5

    for SCREEN in "${SCREENS[@]}"; do
      echo "[screenshots] Capturing ${SCREEN} on ${SIMULATOR}"

      # Run Detox test targeting specific screen
      # Each Detox test in apps/mobile/e2e/screenshots/${SCREEN}.e2e.ts
      # takes a screenshot via device.takeScreenshot(SCREEN)
      npx detox test \
        --configuration "ios.release" \
        --testPathPattern "e2e/screenshots/${SCREEN}" \
        --artifacts-location "${IOS_DIR}/${SAFE_NAME}/" \
        --take-screenshots all \
        --record-logs failing \
        2>&1 | tail -20

      # Rename generated screenshot to consistent name
      SCREENSHOT_FILE=$(find "${IOS_DIR}/${SAFE_NAME}" -name "*.png" -newer /tmp/.screenshot_marker 2>/dev/null | head -1)
      if [[ -n "${SCREENSHOT_FILE}" ]]; then
        mv "${SCREENSHOT_FILE}" "${IOS_DIR}/${SAFE_NAME}/${SCREEN}.png"
        echo "[screenshots] Saved: ${IOS_DIR}/${SAFE_NAME}/${SCREEN}.png"
      fi
    done

    xcrun simctl shutdown "${SIMULATOR}" 2>/dev/null || true
  done

  echo "[screenshots] iOS capture complete. Files in ${IOS_DIR}/"
}

# ---------------------------------------------------------------------------
# Android screenshot capture
# ---------------------------------------------------------------------------
capture_android() {
  echo "[screenshots] Starting Android capture..."
  mkdir -p "${ANDROID_DIR}"

  for AVD in "${ANDROID_AVDS[@]}"; do
    SAFE_NAME="${AVD//-/_}"
    mkdir -p "${ANDROID_DIR}/${SAFE_NAME}"

    echo "[screenshots] Starting emulator: ${AVD}"
    "${ANDROID_HOME}/emulator/emulator" -avd "${AVD}" -no-audio -no-boot-anim &
    EMULATOR_PID=$!
    adb wait-for-device
    sleep 10 # extra boot time

    for SCREEN in "${SCREENS[@]}"; do
      echo "[screenshots] Capturing ${SCREEN} on ${AVD}"

      npx detox test \
        --configuration "android.release" \
        --testPathPattern "e2e/screenshots/${SCREEN}" \
        --artifacts-location "${ANDROID_DIR}/${SAFE_NAME}/" \
        --take-screenshots all \
        2>&1 | tail -20

      SCREENSHOT_FILE=$(find "${ANDROID_DIR}/${SAFE_NAME}" -name "*.png" -newer /tmp/.screenshot_marker 2>/dev/null | head -1)
      if [[ -n "${SCREENSHOT_FILE}" ]]; then
        mv "${SCREENSHOT_FILE}" "${ANDROID_DIR}/${SAFE_NAME}/${SCREEN}.png"
        echo "[screenshots] Saved: ${ANDROID_DIR}/${SAFE_NAME}/${SCREEN}.png"
      fi
    done

    kill "${EMULATOR_PID}" 2>/dev/null || true
  done

  echo "[screenshots] Android capture complete. Files in ${ANDROID_DIR}/"
}

# ---------------------------------------------------------------------------
# Validate output
# ---------------------------------------------------------------------------
validate_screenshots() {
  echo "[screenshots] Validating output..."
  local missing=0

  if [[ "${PLATFORM}" == "ios" || "${PLATFORM}" == "all" ]]; then
    for SIMULATOR in "${IOS_SIMULATORS[@]}"; do
      SAFE_NAME="${SIMULATOR// /_}"
      for SCREEN in "${SCREENS[@]}"; do
        FILE="${IOS_DIR}/${SAFE_NAME}/${SCREEN}.png"
        if [[ ! -f "${FILE}" ]]; then
          echo "[ERROR] Missing: ${FILE}"
          missing=$((missing + 1))
        fi
      done
    done
  fi

  if [[ "${PLATFORM}" == "android" || "${PLATFORM}" == "all" ]]; then
    for AVD in "${ANDROID_AVDS[@]}"; do
      SAFE_NAME="${AVD//-/_}"
      for SCREEN in "${SCREENS[@]}"; do
        FILE="${ANDROID_DIR}/${SAFE_NAME}/${SCREEN}.png"
        if [[ ! -f "${FILE}" ]]; then
          echo "[ERROR] Missing: ${FILE}"
          missing=$((missing + 1))
        fi
      done
    done
  fi

  if [[ "${missing}" -gt 0 ]]; then
    echo "[screenshots] FAILED: ${missing} screenshots missing."
    exit 1
  fi

  echo "[screenshots] All screenshots captured successfully."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
touch /tmp/.screenshot_marker

case "${PLATFORM}" in
  ios)
    capture_ios
    ;;
  android)
    capture_android
    ;;
  all)
    capture_ios
    capture_android
    ;;
  *)
    echo "Usage: $0 [ios|android|all]"
    exit 1
    ;;
esac

validate_screenshots
echo "[screenshots] Done. Review files in ${SCREENSHOT_DIR}/ before uploading."
