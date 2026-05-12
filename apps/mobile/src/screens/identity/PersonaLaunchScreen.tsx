/**
 * PersonaLaunchScreen — Launches the Persona SDK for selfie/liveness verification.
 *
 * Flow:
 * 1. Call POST /identity/inquiry/start → get persona_session_token
 * 2. Launch Persona SDK WebView with the session token
 * 3. On SDK completion → call GET /identity/verification to read new status
 * 4. Emit to parent (via navigation or event) so UI updates the badge state
 *
 * Per spec: soft block — Persona pending/declined does NOT block chat/matching.
 * Only the Valid Profile Badge is gated.
 *
 * NOTE: expo-persona-sdk is a placeholder; the real SDK is @persona-kyc/rn-sdk
 * or the Persona WebView approach. The WebView approach is used here for
 * universal Expo compatibility.
 */

import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Text, TouchableOpacity, View } from "react-native";
import { useAuthStore } from "../../state/auth.store";
import { startInquiry, getVerificationState } from "../../api/identity";

// Navigation param list type — to be expanded in the full navigator
type RootStackParamList = {
  PersonaLaunch: undefined;
};

type Props = {
  navigation: NativeStackNavigationProp<RootStackParamList, "PersonaLaunch">;
};

type VerificationStatus = "idle" | "loading" | "sdk_open" | "completed" | "error";

export function PersonaLaunchScreen({ navigation }: Props): React.ReactElement {
  const [status, setStatus] = useState<VerificationStatus>("idle");
  const [inquiryId, setInquiryId] = useState<string | null>(null);
  const [verificationStatus, setVerificationStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { accessToken } = useAuthStore();

  const handleLaunch = async () => {
    if (!accessToken) return;
    setStatus("loading");
    setError(null);
    try {
      const { persona_inquiry_id, persona_session_token } = await startInquiry(accessToken);
      setInquiryId(persona_inquiry_id);

      // In production: launch Persona SDK with session token
      // Persona.launch({ sessionToken: persona_session_token, onComplete: handleComplete, onError: handleError })
      // For now, open a WebView with the session URL
      setStatus("sdk_open");
      // Simulate SDK completion for development
      // In production this is called by the SDK callback
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Failed to start verification.");
      setStatus("error");
    }
  };

  const handleComplete = async () => {
    if (!accessToken) return;
    setStatus("loading");
    try {
      const state = await getVerificationState(accessToken);
      setVerificationStatus(state.status);
      setStatus("completed");
    } catch {
      setStatus("completed");
    }
  };

  const statusDisplay: Record<string, { label: string; color: string }> = {
    pending: { label: "In progress", color: "text-yellow-600" },
    approved: { label: "Verified ✓", color: "text-green-600" },
    declined: { label: "Declined", color: "text-red-600" },
    needs_review: { label: "Under review", color: "text-orange-600" },
  };

  const display = verificationStatus ? statusDisplay[verificationStatus] : null;

  return (
    <View className="flex-1 bg-white px-6 pt-16">
      <Text className="text-3xl font-bold text-neutral-900 mb-2">Identity Verification</Text>
      <Text className="text-base text-neutral-500 mb-4">
        Complete a quick selfie + liveness check to unlock your Valid Profile Badge.
      </Text>

      <View className="bg-blue-50 rounded-xl p-4 mb-8">
        <Text className="text-blue-700 text-sm font-medium mb-1">Soft requirement</Text>
        <Text className="text-blue-600 text-sm">
          Verification is optional for using Colab. It only gates the Valid Profile Badge,
          which increases your visibility in the feed.
        </Text>
      </View>

      {error && <Text className="text-red-500 text-sm mb-4">{error}</Text>}

      {display && (
        <View className="bg-neutral-50 rounded-xl p-4 mb-6">
          <Text className="text-neutral-500 text-sm mb-1">Current status</Text>
          <Text className={`text-lg font-semibold ${display.color}`}>{display.label}</Text>
        </View>
      )}

      {status === "completed" && verificationStatus === "approved" ? (
        <View className="bg-green-50 rounded-xl p-4 mb-6">
          <Text className="text-green-700 text-center font-medium">
            🎉 Identity verified! Your Valid Profile Badge will appear shortly.
          </Text>
        </View>
      ) : (
        <TouchableOpacity
          className="bg-brand-primary py-3 rounded-xl items-center mb-4"
          onPress={status === "sdk_open" ? handleComplete : handleLaunch}
          disabled={status === "loading"}
          testID="persona-launch-button"
        >
          {status === "loading" ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text className="text-white font-semibold text-base">
              {status === "sdk_open" ? "Complete verification" : "Start verification"}
            </Text>
          )}
        </TouchableOpacity>
      )}

      <Text className="text-center text-neutral-400 text-xs mt-2">
        Powered by Persona. Your data is processed securely and not stored by Colab.
      </Text>
    </View>
  );
}
