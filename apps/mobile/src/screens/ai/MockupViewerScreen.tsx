/**
 * MockupViewerScreen — full-screen AI Collab Preview viewer.
 *
 * Screenshot protection:
 * - Android: FLAG_SECURE applied via native module (blocks hardware screenshot + ADB screencap)
 * - iOS: UIApplicationUserDidTakeScreenshotNotification → overlay warning + audit log POST
 *
 * Watermark overlay: semi-transparent "Colab Preview" text rendered client-side
 * as an extra UX reminder (server-side watermark is the authoritative one).
 *
 * Viewer-only: no download button, no share sheet for the asset URL.
 *
 * Spec: §8 Screenshot Guard, §10.4 GET /collabs/{id}/mockups, §10.5 screenshot-event
 */

import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  Image,
  NativeEventEmitter,
  NativeModules,
  Platform,
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

interface MockupAsset {
  id: string;
  kind: "image" | "audio";
  active: boolean;
  generated_at: string | null;
  expires_at: string | null;
  signed_url: string;
  watermark_present: boolean;
}

interface Props {
  assetId: string;
  collabId: string;
  onClose: () => void;
}

// Native module provided by a custom Expo plugin / bare RN module.
// Stub types — actual implementation in native/MockupScreenshotGuard.*
const MockupScreenshotGuard = NativeModules.MockupScreenshotGuard as {
  enableSecureMode: () => void;
  disableSecureMode: () => void;
} | null;

const ScreenshotGuardEmitter =
  MockupScreenshotGuard
    ? new NativeEventEmitter(NativeModules.MockupScreenshotGuard)
    : null;

export function MockupViewerScreen({ assetId, collabId, onClose }: Props) {
  const [asset, setAsset] = useState<MockupAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [screenshotOverlayVisible, setScreenshotOverlayVisible] = useState(false);
  const overlayOpacity = useRef(new Animated.Value(0)).current;

  // ---------------------------------------------------------------------------
  // Load asset
  // ---------------------------------------------------------------------------
  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch(`/collabs/${collabId}/mockups`);
        if (!resp.ok) throw new Error("Failed to load mockup");
        const data = await resp.json();
        const found = data.mockups?.find((m: MockupAsset) => m.id === assetId);
        setAsset(found ?? null);
      } catch {
        Alert.alert("Error", "Could not load the mockup. Please try again.");
      } finally {
        setLoading(false);
      }
    })();
  }, [assetId, collabId]);

  // ---------------------------------------------------------------------------
  // Screenshot guard setup
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (Platform.OS === "android" && MockupScreenshotGuard) {
      // Enable FLAG_SECURE to block hardware screenshots + ADB screencap
      MockupScreenshotGuard.enableSecureMode();
      return () => {
        MockupScreenshotGuard.disableSecureMode();
      };
    }

    if (Platform.OS === "ios" && ScreenshotGuardEmitter) {
      const sub = ScreenshotGuardEmitter.addListener(
        "onScreenshotDetected",
        ({ assetId: detectedAssetId }: { assetId: string }) => {
          if (detectedAssetId !== assetId) return;
          _handleScreenshotDetected();
        },
      );
      return () => sub.remove();
    }

    return undefined;
  }, [assetId]);

  const _handleScreenshotDetected = () => {
    // Show overlay warning
    setScreenshotOverlayVisible(true);
    Animated.sequence([
      Animated.timing(overlayOpacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      Animated.delay(3000),
      Animated.timing(overlayOpacity, { toValue: 0, duration: 400, useNativeDriver: true }),
    ]).start(() => setScreenshotOverlayVisible(false));

    // Fire-and-forget audit POST
    fetch(`/ai/mockups/${assetId}/screenshot-event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "ios",
        detected_at: new Date().toISOString(),
      }),
    }).catch(() => {
      // Queue for retry via offline queue — best-effort
    });
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <ActivityIndicator size="large" color="#6c5ce7" />
      </SafeAreaView>
    );
  }

  if (!asset) {
    return (
      <SafeAreaView style={styles.centered}>
        <Text style={styles.errorText}>Mockup not available.</Text>
        <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
          <Text style={styles.closeBtnText}>Close</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  const isExpired = !asset.active;

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
          <Text style={styles.closeBtnText}>Done</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>AI Preview</Text>
        <View style={styles.headerSpacer} />
      </View>

      {/* Expired banner */}
      {isExpired && (
        <View style={styles.expiredBanner}>
          <Text style={styles.expiredText}>
            This preview has expired and is no longer viewable.
          </Text>
        </View>
      )}

      {/* Main content — viewer-only, no download */}
      {!isExpired && asset.kind === "image" && (
        <View style={styles.imageContainer}>
          <Image
            source={{ uri: asset.signed_url }}
            style={styles.mockupImage}
            resizeMode="contain"
          />
          {/* Client-side watermark overlay (UX reminder; server watermark is authoritative) */}
          <View style={styles.watermarkOverlay} pointerEvents="none">
            <Text style={styles.watermarkText}>Colab Preview — Watermarked</Text>
          </View>
        </View>
      )}

      {/* Metadata */}
      {!isExpired && (
        <View style={styles.metaContainer}>
          {asset.expires_at && (
            <Text style={styles.metaText}>
              Expires:{" "}
              {new Date(asset.expires_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </Text>
          )}
          <Text style={styles.metaText}>
            Watermarked • Viewer-only • No IP rights transferred
          </Text>
        </View>
      )}

      {/* iOS Screenshot overlay warning */}
      {screenshotOverlayVisible && (
        <Animated.View style={[styles.screenshotOverlay, { opacity: overlayOpacity }]}>
          <Text style={styles.screenshotOverlayText}>
            Screenshots of AI mockups are logged.{"\n"}
            This preview is watermarked and for your eyes only.
          </Text>
        </Animated.View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a0a",
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0a0a0a",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#222",
  },
  headerTitle: {
    flex: 1,
    textAlign: "center",
    fontSize: 16,
    fontWeight: "600",
    color: "#fff",
  },
  headerSpacer: {
    width: 60,
  },
  closeBtn: {
    paddingHorizontal: 4,
    paddingVertical: 4,
    minWidth: 60,
  },
  closeBtnText: {
    fontSize: 16,
    color: "#6c5ce7",
    fontWeight: "600",
  },
  expiredBanner: {
    backgroundColor: "#2d2d2d",
    padding: 14,
    alignItems: "center",
  },
  expiredText: {
    color: "#aaa",
    fontSize: 14,
    textAlign: "center",
  },
  imageContainer: {
    flex: 1,
    position: "relative",
  },
  mockupImage: {
    flex: 1,
    width: "100%",
  },
  watermarkOverlay: {
    position: "absolute",
    bottom: 12,
    left: 0,
    right: 0,
    alignItems: "center",
  },
  watermarkText: {
    color: "rgba(255,255,255,0.4)",
    fontSize: 11,
    fontStyle: "italic",
  },
  metaContainer: {
    padding: 12,
    alignItems: "center",
    gap: 4,
  },
  metaText: {
    fontSize: 12,
    color: "#666",
    textAlign: "center",
  },
  errorText: {
    color: "#aaa",
    fontSize: 16,
    marginBottom: 20,
  },
  screenshotOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.85)",
    alignItems: "center",
    justifyContent: "center",
    padding: 40,
    zIndex: 999,
  },
  screenshotOverlayText: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "600",
    textAlign: "center",
    lineHeight: 28,
  },
});
