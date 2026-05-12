/**
 * VerifyScreen — Email verification via 6-digit OTP or magic-link.
 *
 * Receives email via route params.
 * Calls POST /auth/email/verify/finish with the OTP code.
 * Magic-link flow is handled via deep-link in linking.ts.
 */

import type { RouteProp } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useRef, useState } from "react";
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from "react-native";
import type { AuthStackParamList } from "../../navigation/AuthStack";
import { emailVerifyFinish, emailVerifyStart } from "../../api/auth";

type Props = {
  route: RouteProp<AuthStackParamList, "Verify">;
  navigation: NativeStackNavigationProp<AuthStackParamList, "Verify">;
};

export function VerifyScreen({ route, navigation }: Props): React.ReactElement {
  const { email } = route.params;
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleVerify = async () => {
    if (code.length !== 6) {
      setError("Please enter the 6-digit code.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await emailVerifyFinish({ code });
      setSuccess(true);
      // Short delay then navigate to next onboarding step
      setTimeout(() => navigation.navigate("SignIn"), 1500);
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Invalid or expired code.");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setError(null);
    try {
      await emailVerifyStart(email);
    } catch {
      // Silently fail — always show "sent" to avoid enumeration
    } finally {
      setResending(false);
    }
  };

  return (
    <View className="flex-1 bg-white px-6 pt-16">
      <Text className="text-3xl font-bold text-neutral-900 mb-2">Verify your email</Text>
      <Text className="text-base text-neutral-500 mb-8">
        We sent a 6-digit code to{" "}
        <Text className="text-neutral-900 font-medium">{email}</Text>
      </Text>

      <TextInput
        className="border border-neutral-200 rounded-xl px-4 py-3 mb-4 text-base text-center tracking-widest"
        placeholder="000000"
        keyboardType="number-pad"
        maxLength={6}
        value={code}
        onChangeText={setCode}
        testID="otp-input"
      />

      {error && <Text className="text-red-500 text-sm mb-4" testID="verify-error">{error}</Text>}
      {success && <Text className="text-green-600 text-sm mb-4">Email verified!</Text>}

      <TouchableOpacity
        className="bg-brand-primary py-3 rounded-xl items-center mb-4"
        onPress={handleVerify}
        disabled={loading}
        testID="verify-submit"
      >
        {loading ? <ActivityIndicator color="#fff" /> : <Text className="text-white font-semibold text-base">Verify</Text>}
      </TouchableOpacity>

      <TouchableOpacity onPress={handleResend} disabled={resending}>
        <Text className="text-center text-neutral-500 text-sm">
          {resending ? "Sending..." : "Didn't receive a code? "}
          {!resending && <Text className="text-brand-primary">Resend</Text>}
        </Text>
      </TouchableOpacity>

      <Text className="text-center text-neutral-400 text-xs mt-6">
        Or click the magic link in the email to verify automatically.
      </Text>
    </View>
  );
}
