/**
 * SignInScreen — Email + password login with Apple/Google/Phone options.
 *
 * Connects to auth-svc POST /auth/login/email.
 * On success: tokens stored in auth.store, user navigated to main tabs.
 *
 * A11y: All interactive elements labeled; error live region; 44pt targets.
 */

import React, { useRef, useState } from "react";
import {
  AccessibilityInfo,
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
  const errorRef = useRef<View>(null);

  const handleLogin = async () => {
    if (!email || !password) {
      const msg = "Please enter your email and password.";
      setError(msg);
      AccessibilityInfo.announceForAccessibility(msg);
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
      const msg = apiError?.error?.message ?? "Login failed. Check your credentials.";
      setError(msg);
      AccessibilityInfo.announceForAccessibility(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-white"
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      accessibilityLabel="Sign in screen"
    >
      <View className="flex-1 px-6 pt-16 pb-8">
        <Text
          className="text-3xl font-bold text-neutral-900 mb-2"
          accessibilityRole="header"
        >
          Welcome back
        </Text>
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
          accessibilityLabel="Email address"
          accessibilityHint="Enter your Colab account email"
          accessibilityRequired
          returnKeyType="next"
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
          accessibilityLabel="Password"
          accessibilityHint="Enter your account password"
          accessibilityRequired
          returnKeyType="done"
          onSubmitEditing={handleLogin}
        />

        <TouchableOpacity
          className="self-end mb-6"
          onPress={() => navigation.navigate("ForgotPassword")}
          accessibilityLabel="Forgot password?"
          accessibilityRole="link"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text className="text-brand-primary text-sm">Forgot password?</Text>
        </TouchableOpacity>

        {error && (
          <View
            ref={errorRef}
            accessibilityLiveRegion="assertive"
            accessibilityRole="alert"
            testID="signin-error"
          >
            <Text className="text-red-500 text-sm mb-4">{error}</Text>
          </View>
        )}

        <TouchableOpacity
          className="bg-brand-primary py-3 rounded-xl items-center mb-4"
          style={{ minHeight: 44 }}
          onPress={handleLogin}
          disabled={loading}
          testID="signin-submit"
          accessibilityLabel={loading ? "Signing in, please wait" : "Sign in"}
          accessibilityRole="button"
          accessibilityState={{ busy: loading, disabled: loading }}
        >
          {loading ? (
            <ActivityIndicator color="#fff" accessibilityLabel="Signing in" />
          ) : (
            <Text className="text-white font-semibold text-base">Sign in</Text>
          )}
        </TouchableOpacity>

        <Text className="text-center text-neutral-400 text-sm mb-4" accessibilityRole="none">
          or continue with
        </Text>
        <View className="flex-row gap-3 mb-8" accessibilityLabel="Social sign-in options">
          <TouchableOpacity
            className="flex-1 border border-neutral-200 py-3 rounded-xl items-center"
            style={{ minHeight: 44 }}
            testID="apple-signin"
            accessibilityLabel="Sign in with Apple"
            accessibilityRole="button"
          >
            <Text className="text-neutral-900 font-medium text-sm" importantForAccessibility="no-hide-descendants"> Apple</Text>
          </TouchableOpacity>
          <TouchableOpacity
            className="flex-1 border border-neutral-200 py-3 rounded-xl items-center"
            style={{ minHeight: 44 }}
            testID="google-signin"
            accessibilityLabel="Sign in with Google"
            accessibilityRole="button"
          >
            <Text className="text-neutral-900 font-medium text-sm" importantForAccessibility="no-hide-descendants">G Google</Text>
          </TouchableOpacity>
          <TouchableOpacity
            className="flex-1 border border-neutral-200 py-3 rounded-xl items-center"
            style={{ minHeight: 44 }}
            testID="phone-signin"
            onPress={() => navigation.navigate("PhoneOTP", { phone: "", flow: "login" })}
            accessibilityLabel="Sign in with phone number"
            accessibilityRole="button"
          >
            <Text className="text-neutral-900 font-medium text-sm" importantForAccessibility="no-hide-descendants">📱 Phone</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          onPress={() => navigation.navigate("SignUp")}
          accessibilityLabel="Don't have an account? Sign up"
          accessibilityRole="link"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text className="text-center text-neutral-500 text-sm">
            Don't have an account? <Text className="text-brand-primary font-medium">Sign up</Text>
          </Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}
