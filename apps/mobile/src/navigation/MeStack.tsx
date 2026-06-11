import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { View, Text, TouchableOpacity, ScrollView } from "react-native";
import { ProfileViewScreen } from "../screens/profile/ProfileViewScreen";
import { ProfileSetupWizardScreen } from "../screens/profile/ProfileSetupWizardScreen";
import { PortfolioUploadScreen } from "../screens/profile/PortfolioUploadScreen";
import { VocationPickerScreen } from "../screens/profile/VocationPickerScreen";
import { PersonalityQuizScreen } from "../screens/profile/PersonalityQuizScreen";
import { OAuthConnectScreen } from "../screens/profile/OAuthConnectScreen";
import { PersonaLaunchScreen } from "../screens/identity/PersonaLaunchScreen";
import { EmailChangeScreen } from "../screens/account/EmailChangeScreen";
import { SessionsScreen } from "../screens/account/SessionsScreen";
import { PaywallScreen } from "../screens/billing/PaywallScreen";
import { SubscriptionManagementScreen } from "../screens/billing/SubscriptionManagementScreen";
import { CreditPurchaseScreen } from "../screens/billing/CreditPurchaseScreen";
import { RefundRequestScreen } from "../screens/billing/RefundRequestScreen";
import { FaqListScreen } from "../screens/support/FaqListScreen";
import { TicketListScreen } from "../screens/support/TicketListScreen";
import { TicketFormScreen } from "../screens/support/TicketFormScreen";
import { TicketDetailScreen } from "../screens/support/TicketDetailScreen";
import { ChatbotScreen } from "../screens/support/ChatbotScreen";
import { CSATPromptScreen } from "../screens/support/CSATPromptScreen";

export type MeStackParamList = {
  MeRoot: undefined;
  ProfileView: { profileHandle?: string } | undefined;
  ProfileSetupWizard: undefined;
  PortfolioUpload: undefined;
  VocationPicker: undefined;
  PersonalityQuiz: undefined;
  OAuthConnect: undefined;
  PersonaLaunch: undefined;
  EmailChange: undefined;
  Sessions: undefined;
  Paywall: undefined;
  Subscription: undefined;
  CreditPurchase: undefined;
  RefundRequest: undefined;
  Faqs: undefined;
  Tickets: undefined;
  TicketForm: { suggestedCategory?: string } | undefined;
  TicketDetail: { ticketId: string };
  Chatbot: { ticketId?: string } | undefined;
  CSAT: { ticketId: string };
};

const Stack = createNativeStackNavigator<MeStackParamList>();

function Row({ label, onPress }: { label: string; onPress: () => void }): React.ReactElement {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={{ paddingVertical: 14, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: "#eee" }}
    >
      <Text style={{ fontSize: 16, color: "#222" }}>{label}</Text>
    </TouchableOpacity>
  );
}

function MeRootScreen({ navigation }: { navigation: any }): React.ReactElement {
  return (
    <ScrollView style={{ flex: 1, backgroundColor: "#fff" }}>
      <View style={{ paddingTop: 60, paddingHorizontal: 16, paddingBottom: 12 }}>
        <Text style={{ fontSize: 24, fontWeight: "600" }}>Me</Text>
      </View>
      <Row label="View profile" onPress={() => navigation.navigate("ProfileView")} />
      <Row label="Complete profile" onPress={() => navigation.navigate("ProfileSetupWizard")} />
      <Row label="Portfolio" onPress={() => navigation.navigate("PortfolioUpload")} />
      <Row label="Vocations" onPress={() => navigation.navigate("VocationPicker")} />
      <Row label="Personality quiz" onPress={() => navigation.navigate("PersonalityQuiz")} />
      <Row label="Connect socials" onPress={() => navigation.navigate("OAuthConnect")} />
      <Row label="Verify identity" onPress={() => navigation.navigate("PersonaLaunch")} />
      <Row label="Email" onPress={() => navigation.navigate("EmailChange")} />
      <Row label="Sessions" onPress={() => navigation.navigate("Sessions")} />
      <Row label="Subscription" onPress={() => navigation.navigate("Subscription")} />
      <Row label="Credits" onPress={() => navigation.navigate("CreditPurchase")} />
      <Row label="Paywall" onPress={() => navigation.navigate("Paywall")} />
      <Row label="Refunds" onPress={() => navigation.navigate("RefundRequest")} />
      <Row label="Help & support" onPress={() => navigation.navigate("Faqs")} />
      <Row label="Support tickets" onPress={() => navigation.navigate("Tickets")} />
      <Row label="Chat with support" onPress={() => navigation.navigate("Chatbot")} />
    </ScrollView>
  );
}

export function MeStack(): React.ReactElement {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="MeRoot" component={MeRootScreen} />
      <Stack.Screen name="ProfileView" component={ProfileViewScreen as any} />
      <Stack.Screen name="ProfileSetupWizard" component={ProfileSetupWizardScreen as any} />
      <Stack.Screen name="PortfolioUpload" component={PortfolioUploadScreen as any} />
      <Stack.Screen name="VocationPicker" component={VocationPickerScreen as any} />
      <Stack.Screen name="PersonalityQuiz" component={PersonalityQuizScreen as any} />
      <Stack.Screen name="OAuthConnect" component={OAuthConnectScreen as any} />
      <Stack.Screen name="PersonaLaunch" component={PersonaLaunchScreen as any} />
      <Stack.Screen name="EmailChange" component={EmailChangeScreen} />
      <Stack.Screen name="Sessions" component={SessionsScreen} />
      <Stack.Screen name="Paywall" component={PaywallScreen as any} />
      <Stack.Screen name="Subscription" component={SubscriptionManagementScreen as any} />
      <Stack.Screen name="CreditPurchase" component={CreditPurchaseScreen as any} />
      <Stack.Screen name="RefundRequest" component={RefundRequestScreen as any} />
      <Stack.Screen name="Faqs" component={FaqListScreen as any} />
      <Stack.Screen name="Tickets" component={TicketListScreen as any} />
      <Stack.Screen name="TicketForm" component={TicketFormScreen as any} />
      <Stack.Screen name="TicketDetail" component={TicketDetailScreen as any} />
      <Stack.Screen name="Chatbot" component={ChatbotScreen as any} />
      <Stack.Screen name="CSAT" component={CSATPromptScreen as any} />
    </Stack.Navigator>
  );
}
