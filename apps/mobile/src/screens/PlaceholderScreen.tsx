import React from "react";
import { Text, View } from "react-native";

export function PlaceholderScreen(): React.ReactElement {
  return (
    <View className="flex-1 bg-white items-center justify-center">
      <Text className="text-base text-neutral-400">Coming soon</Text>
    </View>
  );
}
