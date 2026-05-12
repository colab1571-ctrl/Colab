import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  Text,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";

interface PartnerStub {
  profile_id: string;
  display_name: string;
  avatar_url: string | null;
}

interface CollabItem {
  id: string;
  title: string | null;
  status: "still_deciding" | "in_progress";
  is_read_only: boolean;
  last_activity_at: string;
  archived_at: string | null;
  partner: PartnerStub;
  created_at: string;
}

interface CollabListResponse {
  data: CollabItem[];
  next_cursor: string | null;
  total_count: number;
}

function useActiveCollabs() {
  const [collabs, setCollabs] = useState<CollabItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchCollabs = useCallback(
    async (cursor: string | null = null, replace = false) => {
      try {
        const params = new URLSearchParams({ status: "active", limit: "20" });
        if (cursor) params.set("cursor", cursor);

        const resp = await fetch(`/collabs?${params.toString()}`, {
          headers: { "Content-Type": "application/json" },
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data: CollabListResponse = await resp.json();

        setCollabs((prev) => (replace ? data.data : [...prev, ...data.data]));
        setNextCursor(data.next_cursor);
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    []
  );

  useEffect(() => {
    fetchCollabs(null, true);
  }, [fetchCollabs]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    fetchCollabs(null, true);
  }, [fetchCollabs]);

  const loadMore = useCallback(() => {
    if (nextCursor) fetchCollabs(nextCursor, false);
  }, [fetchCollabs, nextCursor]);

  return { collabs, loading, refreshing, error, refresh, loadMore, nextCursor };
}

function statusLabel(status: string): string {
  switch (status) {
    case "still_deciding":
      return "Still Deciding";
    case "in_progress":
      return "In Progress";
    default:
      return status;
  }
}

function statusColor(status: string): string {
  return status === "in_progress" ? "#4f46e5" : "#f59e0b";
}

export function ActiveProjectsScreen(): React.ReactElement {
  const navigation = useNavigation<any>();
  const { collabs, loading, refreshing, error, refresh, loadMore, nextCursor } =
    useActiveCollabs();

  if (loading) {
    return (
      <View className="flex-1 bg-white items-center justify-center">
        <ActivityIndicator size="large" color="#4f46e5" />
      </View>
    );
  }

  if (error) {
    return (
      <View className="flex-1 bg-white items-center justify-center px-6">
        <Text className="text-red-500 text-center">{error}</Text>
        <Pressable
          onPress={refresh}
          className="mt-4 bg-indigo-600 px-6 py-3 rounded-xl"
        >
          <Text className="text-white font-semibold">Retry</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View className="flex-1 bg-neutral-50">
      <FlatList
        data={collabs}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={refresh} />
        }
        onEndReached={nextCursor ? loadMore : undefined}
        onEndReachedThreshold={0.3}
        ListEmptyComponent={
          <View className="flex-1 items-center justify-center py-24">
            <Text className="text-neutral-400 text-base">
              No active projects yet.
            </Text>
            <Text className="text-neutral-400 text-sm mt-1">
              Match with someone to start collaborating.
            </Text>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable
            onPress={() =>
              navigation.navigate("CollabDetail", { collabId: item.id })
            }
            className="bg-white mx-4 my-2 rounded-2xl shadow-sm overflow-hidden"
          >
            <View className="p-4">
              <View className="flex-row items-center justify-between mb-1">
                <Text className="text-base font-semibold text-neutral-900 flex-1 mr-2" numberOfLines={1}>
                  {item.title ?? `Collab with ${item.partner.display_name}`}
                </Text>
                <View
                  className="px-2 py-1 rounded-full"
                  style={{ backgroundColor: statusColor(item.status) + "20" }}
                >
                  <Text
                    className="text-xs font-medium"
                    style={{ color: statusColor(item.status) }}
                  >
                    {statusLabel(item.status)}
                  </Text>
                </View>
              </View>
              <Text className="text-sm text-neutral-500">
                {item.partner.display_name}
              </Text>
              <Text className="text-xs text-neutral-400 mt-2">
                Last activity:{" "}
                {new Date(item.last_activity_at).toLocaleDateString()}
              </Text>
              {item.is_read_only && (
                <Text className="text-xs text-orange-500 mt-1">
                  Read-only
                </Text>
              )}
            </View>
          </Pressable>
        )}
        contentContainerStyle={
          collabs.length === 0 ? { flex: 1 } : { paddingVertical: 8 }
        }
      />
    </View>
  );
}
