import React, { useState } from "react";
import { Text, TextInput, TouchableOpacity, View } from "react-native";

export function SignInScreen(): React.ReactElement {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  return (
    <View className="flex-1 bg-white px-6 pt-16">
      <Text className="text-2xl font-bold text-neutral-900 mb-8">Welcome back</Text>
      <TextInput
        className="border border-neutral-200 rounded-xl px-4 py-3 mb-4 text-base text-neutral-900"
        placeholder="Email"
        placeholderTextColor="#A0A0A0"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
        autoComplete="email"
      />
      <TextInput
        className="border border-neutral-200 rounded-xl px-4 py-3 mb-6 text-base text-neutral-900"
        placeholder="Password"
        placeholderTextColor="#A0A0A0"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="current-password"
      />
      <TouchableOpacity className="bg-brand-primary py-3 rounded-xl items-center mb-4">
        <Text className="text-white font-semibold text-base">Sign In</Text>
      </TouchableOpacity>
      <Text className="text-center text-sm text-neutral-500 mt-4">
        Auth implementation in P2 (auth-svc spec 003)
      </Text>
    </View>
  );
}
