/**
 * SignInScreen — Email + password login with Apple/Google/Phone options.
 *
 * Connects to auth-svc POST /auth/login/email.
 * On success: tokens stored in auth.store, user navigated to main tabs.
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { AuthStackParamList } from "../../navigation/AuthStack";
import { loginEmail } from "../../api/auth";
import { useAuthStore } from "../../state/auth.store";

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, "SignIn">;
};

export function SignInScreen({ navigation }: Props): React.ReactElement {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { setTokens } = useAuthStore();

  const handleLogin = async () => {
    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const tokens = await loginEmail(email, password);
      await setTokens(tokens.access_token, tokens.refresh_token, {
        userId: tokens.user_id,
        email,
        tier: "free",
        roles: [],
      });
      // Root navigator reacts to isAuthenticated and redirects to main tabs
    } catch (err: unknown) {
      const apiError = err as { error?: { message?: string } };
      setError(apiError?.error?.message ?? "Login failed. Check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-white"
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View className="flex-1 px-6 pt-16 pb-8">
        <Text className="text-3xl font-bold text-neutral-900 mb-2">Welcome back</Text>
        <Text className="text-base text-neutral-500 mb-8">Sign in to your Colab account.</Text>

        <TextInput
          className="border border-neutral-200 rounded-xl px-4 py-3 mb-4 text-base text-neutral-900"
          placeholder="Email address"
          placeholderTextColor="#A0A0A0"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          autoComplete="email"
          testID="signin-email-input"
        />
        <TextInput
          className="border border-neutral-200 rounded-xl px-4 py-3 mb-2 text-base text-neutral-900"
          placeholder="Password"
          placeholderTextColor="#A0A0A0"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="current-password"
          testID="signin-password-input"
        />

        <TouchableOpacity className="self-end mb-6" onPress={() => navigation.navigate("ForgotPassword")}>
          <Text className="text-brand-primary text-sm">Forgot password?</Text>
        </TouchableOpacity>

        {error && <Text className="text-red-500 text-sm mb-4" testID="signin-error">{error}</Text>}

        <TouchableOpacity
          className="bg-brand-primary py-3 rounded-xl items-center mb-4"
          onPress={handleLogin}
          disabled={loading}
          testID="signin-submit"
        >
          {loading ? <ActivityIndicator color="#fff" /> : <Text className="text-white font-semibold text-base">Sign in</Text>}
        </TouchableOpacity>

        <Text className="text-center text-neutral-400 text-sm mb-4">or continue with</Text>
        <View className="flex-row gap-3 mb-8">
          <TouchableOpacity className="flex-1 border border-neutral-200 py-3 rounded-xl items-center" testID="apple-signin">
            <Text className="text-neutral-900 font-medium text-sm"> Apple</Text>
          </TouchableOpacity>
          <TouchableOpacity className="flex-1 border border-neutral-200 py-3 rounded-xl items-center" testID="google-signin">
            <Text className="text-neutral-900 font-medium text-sm">G Google</Text>
          </TouchableOpacity>
          <TouchableOpacity className="flex-1 border border-neutral-200 py-3 rounded-xl items-center" testID="phone-signin"
            onPress={() => navigation.navigate("PhoneOTP", { phone: "", flow: "login" })}>
            <Text className="text-neutral-900 font-medium text-sm">📱 Phone</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity onPress={() => navigation.navigate("SignUp")}>
          <Text className="text-center text-neutral-500 text-sm">
            Don't have an account? <Text className="text-brand-primary font-medium">Sign up</Text>
          </Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}
