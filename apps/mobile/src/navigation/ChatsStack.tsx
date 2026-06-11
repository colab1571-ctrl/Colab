import { createNativeStackNavigator } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React from "react";
import { View, Text, TouchableOpacity, FlatList } from "react-native";
import { InboxScreen } from "../screens/invites/InboxScreen";
import { ChatRoomScreen } from "../screens/chat/ChatRoomScreen";
import { MatchCelebrationHandoff } from "../screens/chat/MatchCelebrationHandoff";
import { SlashCommandPicker } from "../screens/chat/SlashCommandPicker";

export type ChatsStackParamList = {
  ChatList: undefined;
  ChatRoom: {
    roomId: string;
    collaborationId: string;
    otherParticipant: {
      profile_id: string;
      display_name: string | null;
      avatar_url: string | null;
    };
  };
  MatchHandoff: {
    matchData: {
      room_id: string;
      collaboration_id: string;
      other_profile: {
        profile_id: string;
        display_name: string | null;
        avatar_url: string | null;
      };
    };
  };
  SlashCommands: { userTier?: "free" | "premium" | "pro" };
};

const Stack = createNativeStackNavigator<ChatsStackParamList>();

/** Lightweight chat list using inbox for now — taps open ChatRoom. */
function ChatListScreen({ navigation }: { navigation: any }): React.ReactElement {
  return (
    <View style={{ flex: 1, backgroundColor: "#fff" }}>
      <InboxScreen navigation={navigation} />
    </View>
  );
}

function ChatRoomRoute({ route }: { route: RouteProp<ChatsStackParamList, "ChatRoom"> }): React.ReactElement {
  const { roomId, collaborationId, otherParticipant } = route.params;
  return (
    <ChatRoomScreen
      roomId={roomId}
      collaborationId={collaborationId}
      otherParticipant={otherParticipant}
    />
  );
}

function MatchHandoffRoute({
  navigation,
  route,
}: {
  navigation: any;
  route: RouteProp<ChatsStackParamList, "MatchHandoff">;
}): React.ReactElement {
  return (
    <MatchCelebrationHandoff
      matchData={route.params.matchData}
      onOpenChat={(roomId, collaborationId, otherProfile) =>
        navigation.replace("ChatRoom", { roomId, collaborationId, otherParticipant: otherProfile })
      }
      onDismiss={() => navigation.goBack()}
    />
  );
}

function SlashCommandsRoute({
  navigation,
  route,
}: {
  navigation: any;
  route: RouteProp<ChatsStackParamList, "SlashCommands">;
}): React.ReactElement {
  return (
    <View style={{ flex: 1, backgroundColor: "#fff", paddingTop: 60 }}>
      <SlashCommandPicker
        userTier={route.params?.userTier ?? "free"}
        onSelectCommand={() => navigation.goBack()}
      />
    </View>
  );
}

export function ChatsStack(): React.ReactElement {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="ChatList" component={ChatListScreen} />
      <Stack.Screen name="ChatRoom" component={ChatRoomRoute} />
      <Stack.Screen name="MatchHandoff" component={MatchHandoffRoute} options={{ presentation: "modal" }} />
      <Stack.Screen name="SlashCommands" component={SlashCommandsRoute} options={{ presentation: "modal" }} />
    </Stack.Navigator>
  );
}
