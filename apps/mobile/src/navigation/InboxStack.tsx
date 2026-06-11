import { createNativeStackNavigator } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React, { useState } from "react";
import { View } from "react-native";
import { InboxScreen } from "../screens/invites/InboxScreen";
import { SentHistoryScreen } from "../screens/invites/SentHistoryScreen";
import { BlocksScreen } from "../screens/invites/BlocksScreen";
import { MatchCelebrationScreen } from "../screens/invites/MatchCelebrationScreen";
import { SendVibeCheckModal } from "../screens/invites/SendVibeCheckModal";

export type InboxStackParamList = {
  Inbox: undefined;
  Sent: undefined;
  Blocks: undefined;
  MatchCelebration: {
    profileId: string;
    displayName: string | null;
    avatarUrl: string | null;
  };
  SendVibeCheck: { toProfileId: string; toDisplayName: string | null };
};

const Stack = createNativeStackNavigator<InboxStackParamList>();

function SendVibeCheckRoute({
  navigation,
  route,
}: {
  navigation: any;
  route: RouteProp<InboxStackParamList, "SendVibeCheck">;
}): React.ReactElement {
  const [visible, setVisible] = useState(true);
  return (
    <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.4)" }}>
      <SendVibeCheckModal
        visible={visible}
        toProfileId={route.params.toProfileId}
        toDisplayName={route.params.toDisplayName}
        navigation={navigation}
        onClose={() => {
          setVisible(false);
          navigation.goBack();
        }}
      />
    </View>
  );
}

export function InboxStack(): React.ReactElement {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Inbox" component={InboxScreen} />
      <Stack.Screen name="Sent" component={SentHistoryScreen} />
      <Stack.Screen name="Blocks" component={BlocksScreen} />
      <Stack.Screen name="MatchCelebration" component={MatchCelebrationScreen} options={{ presentation: "modal" }} />
      <Stack.Screen name="SendVibeCheck" component={SendVibeCheckRoute} options={{ presentation: "modal" }} />
    </Stack.Navigator>
  );
}
