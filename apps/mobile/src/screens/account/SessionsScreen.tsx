/**
 * SessionsScreen — List active sessions + revoke individual sessions.
 * Also provides "Log out all devices" action.
 *
 * Connects to GET /auth/sessions, DELETE /auth/sessions/{id}, POST /auth/logout/all.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { getSessions, revokeSession, logoutAll } from "../../api/auth";
import { useAuthStore } from "../../state/auth.store";

interface SessionItem {
  id: string;
  user_agent: string | null;
  ip: string | null;
  last_seen_at: string;
  created_at: string;
  is_current: boolean;
}

export function SessionsScreen(): React.ReactElement {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { clearTokens } = useAuthStore();

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getSessions();
      setSessions(result.sessions);
    } catch {
      setError("Failed to load sessions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleRevoke = async (sessionId: string) => {
    try {
      const result = await revokeSession(sessionId);
      setSessions(result.sessions);
    } catch {
      Alert.alert("Error", "Failed to revoke session.");
    }
  };

  const handleLogoutAll = async () => {
    Alert.alert(
      "Log out all devices",
      "This will sign you out from all devices, including this one.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Log out all",
          style: "destructive",
          onPress: async () => {
            try {
              await logoutAll();
              await clearTokens();
            } catch {
              Alert.alert("Error", "Failed to log out all devices.");
            }
          },
        },
      ]
    );
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  };

  if (loading) {
    return (
      <View className="flex-1 bg-white items-center justify-center">
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <View className="flex-1 bg-neutral-50">
      <FlatList
        data={sessions}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ padding: 16 }}
        ListHeaderComponent={
          <View className="mb-4">
            <Text className="text-2xl font-bold text-neutral-900 mb-1">Active sessions</Text>
            <Text className="text-sm text-neutral-500">{sessions.length} active session(s)</Text>
          </View>
        }
        ListFooterComponent={
          <TouchableOpacity
            className="bg-red-50 border border-red-200 py-3 rounded-xl items-center mt-4"
            onPress={handleLogoutAll}
            testID="logout-all-button"
          >
            <Text className="text-red-600 font-medium">Log out all devices</Text>
          </TouchableOpacity>
        }
        renderItem={({ item }) => (
          <View className="bg-white rounded-xl p-4 mb-3 shadow-sm">
            <View className="flex-row items-start justify-between">
              <View className="flex-1 mr-3">
                <Text className="text-sm font-medium text-neutral-900" numberOfLines={1}>
                  {item.user_agent ?? "Unknown device"}
                </Text>
                <Text className="text-xs text-neutral-500 mt-1">
                  IP: {item.ip ?? "unknown"} · Last active: {formatDate(item.last_seen_at)}
                </Text>
                {item.is_current && (
                  <View className="bg-green-100 self-start px-2 py-0.5 rounded mt-1">
                    <Text className="text-green-700 text-xs font-medium">Current session</Text>
                  </View>
                )}
              </View>
              {!item.is_current && (
                <TouchableOpacity
                  onPress={() => handleRevoke(item.id)}
                  testID={`revoke-session-${item.id}`}
                >
                  <Text className="text-red-500 text-sm font-medium">Revoke</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        )}
      />
    </View>
  );
}
