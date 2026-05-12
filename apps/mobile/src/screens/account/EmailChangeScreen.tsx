/**
 * EmailChangeScreen — Change email address flow.
 *
 * Step 1: Enter new email → POST /auth/account/email/change/start
 * Step 2: Enter OTP sent to new email → POST /auth/account/email/change/finish
 */

import React, { useState } from "react";
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from "react-native";
import { emailChangeStart, emailChangeFinish } from "../../api/auth";

export function EmailChangeScreen(): React.ReactElement {
  const [step, setStep] = useState<"start" | "verify">("start");
  const [newEmail, setNewEmail] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const handleStart = async () => {
    if (!newEmail) return;
    setLoading(true);
    setError(null);
    try {
      await emailChangeStart(newEmail);
      setStep("verify");
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Failed to send verification email.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!code || code.length !== 6) {
      setError("Enter the 6-digit code sent to your new email.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await emailChangeFinish({ code });
      setDone(true);
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Invalid or expired code.");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <View className="flex-1 bg-white px-6 pt-16 items-center justify-center">
        <Text className="text-2xl font-bold text-green-600 mb-2">Email updated!</Text>
        <Text className="text-neutral-500 text-center">Your email address has been changed to {newEmail}.</Text>
      </View>
    );
  }

  return (
    <View className="flex-1 bg-white px-6 pt-16">
      <Text className="text-3xl font-bold text-neutral-900 mb-2">Change email</Text>

      {step === "start" ? (
        <>
          <Text className="text-base text-neutral-500 mb-8">Enter your new email address. We'll send a verification code.</Text>
          <TextInput
            className="border border-neutral-200 rounded-xl px-4 py-3 mb-4 text-base"
            placeholder="New email address"
            autoCapitalize="none"
            keyboardType="email-address"
            value={newEmail}
            onChangeText={setNewEmail}
            testID="new-email-input"
          />
        </>
      ) : (
        <>
          <Text className="text-base text-neutral-500 mb-8">Enter the 6-digit code sent to <Text className="text-neutral-900 font-medium">{newEmail}</Text></Text>
          <TextInput
            className="border border-neutral-200 rounded-xl px-4 py-3 mb-4 text-2xl text-center tracking-widest"
            placeholder="000000"
            keyboardType="number-pad"
            maxLength={6}
            value={code}
            onChangeText={setCode}
            testID="email-change-otp-input"
          />
        </>
      )}

      {error && <Text className="text-red-500 text-sm mb-4" testID="email-change-error">{error}</Text>}

      <TouchableOpacity
        className="bg-brand-primary py-3 rounded-xl items-center"
        onPress={step === "start" ? handleStart : handleVerify}
        disabled={loading}
        testID="email-change-submit"
      >
        {loading ? <ActivityIndicator color="#fff" /> : (
          <Text className="text-white font-semibold text-base">
            {step === "start" ? "Send verification code" : "Confirm"}
          </Text>
        )}
      </TouchableOpacity>
    </View>
  );
}
