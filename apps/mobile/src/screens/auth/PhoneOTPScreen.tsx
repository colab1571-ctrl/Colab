/**
 * PhoneOTPScreen — 6-digit OTP entry for phone signup/login.
 *
 * Handles both "signup" and "login" flows via route.params.flow.
 */

import type { RouteProp } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useState } from "react";
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from "react-native";
import type { AuthStackParamList } from "../../navigation/AuthStack";
import { loginPhoneVerify, signupPhoneVerify, loginPhoneStart, signupPhoneStart } from "../../api/auth";
import { useAuthStore } from "../../state/auth.store";

type Props = {
  route: RouteProp<AuthStackParamList, "PhoneOTP">;
  navigation: NativeStackNavigationProp<AuthStackParamList, "PhoneOTP">;
};

export function PhoneOTPScreen({ route, navigation }: Props): React.ReactElement {
  const { phone, flow } = route.params;
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const { setTokens } = useAuthStore();

  const handleVerify = async () => {
    if (code.length !== 6) {
      setError("Enter the 6-digit code.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const verify = flow === "signup" ? signupPhoneVerify : loginPhoneVerify;
      const tokens = await verify(phone, code);
      await setTokens(tokens.access_token, tokens.refresh_token, {
        userId: tokens.user_id,
        email: "",
        tier: "free",
        roles: [],
      });
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Invalid code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    try {
      if (flow === "signup") await signupPhoneStart(phone);
      else await loginPhoneStart(phone);
    } catch {
      // silently handle
    } finally {
      setResending(false);
    }
  };

  return (
    <View className="flex-1 bg-white px-6 pt-16">
      <Text className="text-3xl font-bold text-neutral-900 mb-2">Enter code</Text>
      <Text className="text-base text-neutral-500 mb-8">
        We texted a 6-digit code to <Text className="text-neutral-900 font-medium">{phone}</Text>
      </Text>

      <TextInput
        className="border border-neutral-200 rounded-xl px-4 py-3 mb-4 text-2xl text-center tracking-widest"
        placeholder="000000"
        keyboardType="number-pad"
        maxLength={6}
        value={code}
        onChangeText={setCode}
        testID="phone-otp-input"
      />

      {error && <Text className="text-red-500 text-sm mb-4" testID="phone-otp-error">{error}</Text>}

      <TouchableOpacity
        className="bg-brand-primary py-3 rounded-xl items-center mb-4"
        onPress={handleVerify}
        disabled={loading}
        testID="phone-otp-submit"
      >
        {loading ? <ActivityIndicator color="#fff" /> : <Text className="text-white font-semibold text-base">Verify</Text>}
      </TouchableOpacity>

      <TouchableOpacity onPress={handleResend} disabled={resending}>
        <Text className="text-center text-neutral-500 text-sm">
          {resending ? "Sending..." : <>Didn't receive a code? <Text className="text-brand-primary">Resend</Text></>}
        </Text>
      </TouchableOpacity>
    </View>
  );
}
