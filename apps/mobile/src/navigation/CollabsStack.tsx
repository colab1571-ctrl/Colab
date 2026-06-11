import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React, { useState } from "react";
import { View, Text, TouchableOpacity } from "react-native";
import { ActiveProjectsScreen } from "../screens/collab/ActiveProjectsScreen";
import { PastProjectsScreen } from "../screens/collab/PastProjectsScreen";
import { CollabDetailScreen } from "../screens/collab/CollabDetailScreen";
import TaskListScreen from "../screens/collab/TaskListScreen";
import TaskDetailScreen from "../screens/collab/TaskDetailScreen";
import KanbanView from "../screens/collab/KanbanView";
import { SearchScreen } from "../screens/collab/SearchScreen";
import WhiteboardScreen from "../screens/collab/WhiteboardScreen";
import { ExportStatusScreen } from "../screens/collab/ExportStatusScreen";
import { FeedbackPromptModal } from "../screens/collab/FeedbackPromptModal";
import ScheduleMeetingModal from "../screens/meetings/ScheduleMeetingModal";
import BotConsentDialog from "../screens/meetings/BotConsentDialog";
import MeetingDetailScreen from "../screens/meetings/MeetingDetailScreen";
import { MockupConsentModal } from "../screens/ai/MockupConsentModal";
import { MockupViewerScreen } from "../screens/ai/MockupViewerScreen";

export type CollabsStackParamList = {
  CollabsHome: undefined;
  Past: undefined;
  CollabDetail: { collabId: string };
  TaskList: { collabId: string };
  TaskDetail: { taskId: string };
  Kanban: { collabId: string };
  Search: undefined;
  Whiteboard: { collabId: string };
  ExportStatus: { collabId: string };
  Feedback: { collabId: string };
  ScheduleMeeting: { collabId: string };
  MeetingDetail: { meetingId: string };
  BotConsent: { meetingId: string };
  MockupConsent: { collabId: string; currentUserId: string };
  MockupViewer: { assetId: string; collabId: string };
};

const Stack = createNativeStackNavigator<CollabsStackParamList>();

function CollabsHomeScreen({ navigation }: { navigation: any }): React.ReactElement {
  return (
    <View style={{ flex: 1, backgroundColor: "#fff" }}>
      <View style={{ flexDirection: "row", padding: 12, gap: 8 }}>
        <TouchableOpacity onPress={() => navigation.navigate("Past")}>
          <Text style={{ color: "#5B5BD6" }}>Past projects</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => navigation.navigate("Search")}>
          <Text style={{ color: "#5B5BD6" }}>Search</Text>
        </TouchableOpacity>
      </View>
      <ActiveProjectsScreen />
    </View>
  );
}

function FeedbackRoute({ navigation, route }: { navigation: any; route: any }): React.ReactElement {
  const [visible, setVisible] = useState(true);
  return (
    <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.4)" }}>
      <FeedbackPromptModal
        visible={visible}
        collabId={route.params?.collabId ?? ""}
        onDismiss={() => {
          setVisible(false);
          navigation.goBack();
        }}
      />
    </View>
  );
}

function ScheduleMeetingRoute({
  navigation,
  route,
}: {
  navigation: any;
  route: any;
}): React.ReactElement {
  const [visible, setVisible] = useState(true);
  return (
    <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.4)" }}>
      <ScheduleMeetingModal
        visible={visible}
        collabId={route.params?.collabId ?? ""}
        onClose={() => {
          setVisible(false);
          navigation.goBack();
        }}
        onScheduled={(meeting: { id: string }) => {
          setVisible(false);
          navigation.replace("MeetingDetail", { meetingId: meeting.id });
        }}
      />
    </View>
  );
}

function BotConsentRoute({
  navigation,
  route,
}: {
  navigation: any;
  route: any;
}): React.ReactElement {
  const [visible, setVisible] = useState(true);
  return (
    <BotConsentDialog
      visible={visible}
      meetingId={route.params?.meetingId ?? ""}
      botStatus="none"
      myConsent={false}
      otherParticipantName=""
      otherConsented={false}
      onClose={() => {
        setVisible(false);
        navigation.goBack();
      }}
      onConsentChange={() => {}}
    />
  );
}

function MockupConsentRoute({
  navigation,
  route,
}: {
  navigation: any;
  route: any;
}): React.ReactElement {
  const [visible, setVisible] = useState(true);
  return (
    <MockupConsentModal
      visible={visible}
      collabId={route.params?.collabId ?? ""}
      currentUserId={route.params?.currentUserId ?? ""}
      onClose={() => {
        setVisible(false);
        navigation.goBack();
      }}
    />
  );
}

function KanbanRoute({ route }: { route: any }): React.ReactElement {
  return <KanbanView collabId={route.params?.collabId ?? ""} currentUserId="" />;
}

function MockupViewerRoute({
  navigation,
  route,
}: {
  navigation: any;
  route: any;
}): React.ReactElement {
  return (
    <MockupViewerScreen
      assetId={route.params?.assetId ?? ""}
      collabId={route.params?.collabId ?? ""}
      onClose={() => navigation.goBack()}
    />
  );
}

export function CollabsStack(): React.ReactElement {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="CollabsHome" component={CollabsHomeScreen} />
      <Stack.Screen name="Past" component={PastProjectsScreen} />
      <Stack.Screen name="CollabDetail" component={CollabDetailScreen} />
      <Stack.Screen name="TaskList" component={TaskListScreen} />
      <Stack.Screen name="TaskDetail" component={TaskDetailScreen} />
      <Stack.Screen name="Kanban" component={KanbanRoute} />
      <Stack.Screen name="Search" component={SearchScreen} />
      <Stack.Screen name="Whiteboard" component={WhiteboardScreen} />
      <Stack.Screen name="ExportStatus" component={ExportStatusScreen} />
      <Stack.Screen name="MeetingDetail" component={MeetingDetailScreen} />
      <Stack.Screen name="Feedback" component={FeedbackRoute} options={{ presentation: "modal" }} />
      <Stack.Screen name="ScheduleMeeting" component={ScheduleMeetingRoute} options={{ presentation: "modal" }} />
      <Stack.Screen name="BotConsent" component={BotConsentRoute} options={{ presentation: "modal" }} />
      <Stack.Screen name="MockupConsent" component={MockupConsentRoute} options={{ presentation: "modal" }} />
      <Stack.Screen name="MockupViewer" component={MockupViewerRoute} options={{ presentation: "modal" }} />
    </Stack.Navigator>
  );
}
