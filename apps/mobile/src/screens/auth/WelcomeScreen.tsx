import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React from "react";
import { Text, TouchableOpacity, View } from "react-native";
import type { AuthStackParamList } from "../../navigation/AuthStack";

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, "Welcome">;
};

export function WelcomeScreen({ navigation }: Props): React.ReactElement {
  return (
    <View className="flex-1 bg-white items-center justify-center px-6">
      <Text className="text-4xl font-bold text-brand-primary mb-2">Colab</Text>
      <Text className="text-base text-neutral-500 text-center mb-12">
        The creative collaboration platform for rising artists.
      </Text>
      <TouchableOpacity
        className="w-full bg-brand-primary py-3 rounded-xl items-center mb-4"
        onPress={() => navigation.navigate("SignUp")}
      >
        <Text className="text-white font-semibold text-base">Get started</Text>
      </TouchableOpacity>
      <TouchableOpacity
        className="w-full border border-neutral-200 py-3 rounded-xl items-center"
        onPress={() => navigation.navigate("SignIn")}
      >
        <Text className="text-neutral-700 font-semibold text-base">Sign in</Text>
      </TouchableOpacity>
    </View>
  );
}
