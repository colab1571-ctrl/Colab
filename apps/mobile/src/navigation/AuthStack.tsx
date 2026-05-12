import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { WelcomeScreen } from "../screens/auth/WelcomeScreen";
import { SignInScreen } from "../screens/auth/SignInScreen";
import { SignUpScreen } from "../screens/auth/SignUpScreen";
import { VerifyScreen } from "../screens/auth/VerifyScreen";
import { PhoneOTPScreen } from "../screens/auth/PhoneOTPScreen";
import { ForgotPasswordScreen } from "../screens/auth/ForgotPasswordScreen";

export type AuthStackParamList = {
  Welcome: undefined;
  SignIn: undefined;
  SignUp: undefined;
  Verify: { email: string };
  PhoneOTP: { phone: string; flow: "signup" | "login" };
  ForgotPassword: undefined;
};

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthStack(): React.ReactElement {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Welcome" component={WelcomeScreen} />
      <Stack.Screen name="SignIn" component={SignInScreen} />
      <Stack.Screen name="SignUp" component={SignUpScreen} />
      <Stack.Screen name="Verify" component={VerifyScreen} />
      <Stack.Screen name="PhoneOTP" component={PhoneOTPScreen} />
      <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
    </Stack.Navigator>
  );
}
