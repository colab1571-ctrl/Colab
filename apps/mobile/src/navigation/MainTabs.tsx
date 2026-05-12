import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import React from "react";
import { Text } from "react-native";
import { HomeScreen } from "../screens/home/HomeScreen";
import { PlaceholderScreen } from "../screens/PlaceholderScreen";

export type MainTabsParamList = {
  Home: undefined;
  Discover: undefined;
  Chats: undefined;
  Me: undefined;
};

const Tab = createBottomTabNavigator<MainTabsParamList>();

function TabIcon({ label, focused }: { label: string; focused: boolean }): React.ReactElement {
  return (
    <Text style={{ fontSize: 12, color: focused ? "#5B5BD6" : "#A0A0A0", fontWeight: focused ? "600" : "400" }}>
      {label}
    </Text>
  );
}

export function MainTabs(): React.ReactElement {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: { borderTopColor: "#E0E0E0" },
        tabBarActiveTintColor: "#5B5BD6",
        tabBarInactiveTintColor: "#A0A0A0",
      }}
    >
      <Tab.Screen
        name="Home"
        component={HomeScreen}
        options={{ tabBarLabel: "Home" }}
      />
      <Tab.Screen
        name="Discover"
        component={PlaceholderScreen}
        options={{ tabBarLabel: "Discover" }}
      />
      <Tab.Screen
        name="Chats"
        component={PlaceholderScreen}
        options={{ tabBarLabel: "Chats" }}
      />
      <Tab.Screen
        name="Me"
        component={PlaceholderScreen}
        options={{ tabBarLabel: "Me" }}
      />
    </Tab.Navigator>
  );
}
