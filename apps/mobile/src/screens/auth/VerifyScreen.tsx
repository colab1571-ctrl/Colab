import type { RouteProp } from "@react-navigation/native";
import React from "react";
import { Text, View } from "react-native";
import type { AuthStackParamList } from "../../navigation/AuthStack";

type Props = {
  route: RouteProp<AuthStackParamList, "Verify">;
};

export function VerifyScreen({ route }: Props): React.ReactElement {
  return (
    <View className="flex-1 bg-white items-center justify-center px-6">
      <Text className="text-2xl font-bold text-neutral-900 mb-4">Verify your email</Text>
      <Text className="text-sm text-neutral-500 text-center">
        We sent a 6-digit code to {route.params.email}
      </Text>
    </View>
  );
}
