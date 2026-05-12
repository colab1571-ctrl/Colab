import React from "react";
import { Text, View } from "react-native";

export function SignUpScreen(): React.ReactElement {
  return (
    <View className="flex-1 bg-white items-center justify-center px-6">
      <Text className="text-2xl font-bold text-neutral-900 mb-4">Create Account</Text>
      <Text className="text-sm text-neutral-500 text-center">
        Full signup flow implemented in P2 (auth-svc + profile-svc).
      </Text>
    </View>
  );
}
