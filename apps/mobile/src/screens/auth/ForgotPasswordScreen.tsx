/**
 * ForgotPasswordScreen — Request password reset email.
 *
 * Connects to POST /auth/password/reset/start.
 * Always shows success to avoid email enumeration.
 */

import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useState } from "react";
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from "react-native";
import type { AuthStackParamList } from "../../navigation/AuthStack";
import { passwordResetStart } from "../../api/auth";

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, "ForgotPassword">;
};

export function ForgotPasswordScreen({ navigation }: Props): React.ReactElement {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleReset = async () => {
    if (!email) return;
    setLoading(true);
    try {
      await passwordResetStart(email);
    } catch {
      // Always show success (server never leaks whether email exists)
    } finally {
      setLoading(false);
      setSent(true);
    }
  };

  return (
    <View className="flex-1 bg-white px-6 pt-16">
      <Text className="text-3xl font-bold text-neutral-900 mb-2">Reset password</Text>
      <Text className="text-base text-neutral-500 mb-8">
        Enter your email and we'll send a reset link.
      </Text>

      {!sent ? (
        <>
          <TextInput
            className="border border-neutral-200 rounded-xl px-4 py-3 mb-4 text-base"
            placeholder="Email address"
            autoCapitalize="none"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
            testID="forgot-email-input"
          />
          <TouchableOpacity
            className="bg-brand-primary py-3 rounded-xl items-center"
            onPress={handleReset}
            disabled={loading}
            testID="forgot-submit"
          >
            {loading ? <ActivityIndicator color="#fff" /> : <Text className="text-white font-semibold text-base">Send reset link</Text>}
          </TouchableOpacity>
        </>
      ) : (
        <View className="bg-green-50 rounded-xl p-4 mb-6">
          <Text className="text-green-700 text-center">
            If that email is registered, a reset link is on its way. Check your inbox (and spam folder).
          </Text>
        </View>
      )}

      <TouchableOpacity className="mt-6" onPress={() => navigation.navigate("SignIn")}>
        <Text className="text-center text-neutral-500 text-sm">
          Back to <Text className="text-brand-primary">Sign in</Text>
        </Text>
      </TouchableOpacity>
    </View>
  );
}
