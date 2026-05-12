/**
 * SignUpScreen — Email, Apple, Google, Phone OTP signup.
 *
 * 18+ age attestation is required (enforced server-side too).
 * ToS/Privacy/Community Guidelines accepted on this screen.
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { AuthStackParamList } from "../../navigation/AuthStack";
import { signupEmail, signupPhoneStart } from "../../api/auth";
import { useAuthStore } from "../../state/auth.store";

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, "SignUp">;
};

type SignupMethod = "email" | "phone";

export function SignUpScreen({ navigation }: Props): React.ReactElement {
  const [method, setMethod] = useState<SignupMethod>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [ageAttested, setAgeAttested] = useState(false);
  const [tosAccepted, setTosAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { setTokens } = useAuthStore();

  const handleEmailSignup = async () => {
    if (!ageAttested) {
      setError("You must be 18 or older to use Colab.");
      return;
    }
    if (!tosAccepted) {
      setError("Please accept the Terms of Service and Privacy Policy.");
      return;
    }
    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const tokens = await signupEmail({ email, password });
      await setTokens(tokens.access_token, tokens.refresh_token, {
        userId: tokens.user_id,
        email,
        tier: "free",
        roles: [],
      });
      navigation.navigate("Verify", { email });
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Signup failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handlePhoneSignup = async () => {
    if (!ageAttested) {
      setError("You must be 18 or older to use Colab.");
      return;
    }
    if (!phone) {
      setError("Please enter your phone number in E.164 format (+12125551234).");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await signupPhoneStart(phone);
      navigation.navigate("PhoneOTP", { phone, flow: "signup" });
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Failed to send OTP.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-white"
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <ScrollView className="flex-1" contentContainerStyle={{ flexGrow: 1 }} keyboardShouldPersistTaps="handled">
        <View className="flex-1 px-6 pt-16 pb-8">
          <Text className="text-3xl font-bold text-neutral-900 mb-2">Create account</Text>
          <Text className="text-base text-neutral-500 mb-8">Join Colab — the platform for creative artists.</Text>

          {/* Method selector */}
          <View className="flex-row mb-6 bg-neutral-100 rounded-xl p-1">
            {(["email", "phone"] as SignupMethod[]).map((m) => (
              <TouchableOpacity
                key={m}
                className={`flex-1 py-2 rounded-lg items-center ${method === m ? "bg-white shadow-sm" : ""}`}
                onPress={() => setMethod(m)}
              >
                <Text className={`text-sm font-medium ${method === m ? "text-neutral-900" : "text-neutral-500"}`}>
                  {m === "email" ? "Email" : "Phone"}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {method === "email" ? (
            <>
              <TextInput
                className="border border-neutral-200 rounded-xl px-4 py-3 mb-3 text-base"
                placeholder="Email address"
                autoCapitalize="none"
                keyboardType="email-address"
                autoComplete="email"
                value={email}
                onChangeText={setEmail}
                testID="signup-email-input"
              />
              <TextInput
                className="border border-neutral-200 rounded-xl px-4 py-3 mb-3 text-base"
                placeholder="Password (min 8 characters)"
                secureTextEntry
                autoComplete="new-password"
                value={password}
                onChangeText={setPassword}
                testID="signup-password-input"
              />
            </>
          ) : (
            <TextInput
              className="border border-neutral-200 rounded-xl px-4 py-3 mb-3 text-base"
              placeholder="Phone (+12125551234)"
              keyboardType="phone-pad"
              value={phone}
              onChangeText={setPhone}
              testID="signup-phone-input"
            />
          )}

          {/* 18+ attestation */}
          <TouchableOpacity className="flex-row items-start mb-3" onPress={() => setAgeAttested(!ageAttested)} testID="age-checkbox">
            <View className={`w-5 h-5 rounded border mr-3 mt-0.5 items-center justify-center ${ageAttested ? "bg-brand-primary border-brand-primary" : "border-neutral-300"}`}>
              {ageAttested && <Text className="text-white text-xs font-bold">✓</Text>}
            </View>
            <Text className="flex-1 text-sm text-neutral-600">I confirm I am 18 years of age or older</Text>
          </TouchableOpacity>

          {/* ToS */}
          <TouchableOpacity className="flex-row items-start mb-6" onPress={() => setTosAccepted(!tosAccepted)} testID="tos-checkbox">
            <View className={`w-5 h-5 rounded border mr-3 mt-0.5 items-center justify-center ${tosAccepted ? "bg-brand-primary border-brand-primary" : "border-neutral-300"}`}>
              {tosAccepted && <Text className="text-white text-xs font-bold">✓</Text>}
            </View>
            <Text className="flex-1 text-sm text-neutral-600">
              I agree to the <Text className="text-brand-primary">Terms of Service</Text>,{" "}
              <Text className="text-brand-primary">Privacy Policy</Text>, and{" "}
              <Text className="text-brand-primary">Community Guidelines</Text>
            </Text>
          </TouchableOpacity>

          {error && <Text className="text-red-500 text-sm mb-4" testID="signup-error">{error}</Text>}

          <TouchableOpacity
            className="bg-brand-primary py-3 rounded-xl items-center mb-4"
            onPress={method === "email" ? handleEmailSignup : handlePhoneSignup}
            disabled={loading}
            testID="signup-submit"
          >
            {loading ? <ActivityIndicator color="#fff" /> : <Text className="text-white font-semibold text-base">Create account</Text>}
          </TouchableOpacity>

          <Text className="text-center text-neutral-400 text-sm mb-4">or continue with</Text>
          <View className="flex-row gap-3 mb-8">
            <TouchableOpacity className="flex-1 border border-neutral-200 py-3 rounded-xl items-center" testID="apple-signup">
              <Text className="text-neutral-900 font-medium text-sm"> Apple</Text>
            </TouchableOpacity>
            <TouchableOpacity className="flex-1 border border-neutral-200 py-3 rounded-xl items-center" testID="google-signup">
              <Text className="text-neutral-900 font-medium text-sm">G Google</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity onPress={() => navigation.navigate("SignIn")}>
            <Text className="text-center text-neutral-500 text-sm">
              Already have an account? <Text className="text-brand-primary font-medium">Sign in</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
