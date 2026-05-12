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

interface PastCollabItem {
  id: string;
  title: string | null;
  status: "completed" | "didnt_work_out";
  is_read_only: boolean;
  last_activity_at: string;
  archived_at: string | null;
  partner: PartnerStub;
  created_at: string;
}

interface CollabListResponse {
  data: PastCollabItem[];
  next_cursor: string | null;
  total_count: number;
}

function usePastCollabs() {
  const [collabs, setCollabs] = useState<PastCollabItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchCollabs = useCallback(
    async (cursor: string | null = null, replace = false) => {
      try {
        const params = new URLSearchParams({
          status: "past",
          include_archived: "true",
          limit: "20",
        });
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

function OutcomeBadge({ status }: { status: string }): React.ReactElement {
  const isCompleted = status === "completed";
  return (
    <View
      className={`px-2 py-1 rounded-full ${isCompleted ? "bg-green-100" : "bg-neutral-100"}`}
    >
      <Text
        className={`text-xs font-medium ${isCompleted ? "text-green-700" : "text-neutral-500"}`}
      >
        {isCompleted ? "Completed" : "Didn't Work Out"}
      </Text>
    </View>
  );
}

export function PastProjectsScreen(): React.ReactElement {
  const navigation = useNavigation<any>();
  const { collabs, loading, refreshing, error, refresh, loadMore, nextCursor } =
    usePastCollabs();

  if (loading) {
    return (
      <View className="flex-1 bg-white items-center justify-center">
        <ActivityIndicator size="large" color="#4f46e5" />
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
              No past projects yet.
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
                <Text
                  className="text-base font-semibold text-neutral-900 flex-1 mr-2"
                  numberOfLines={1}
                >
                  {item.title ?? `Collab with ${item.partner.display_name}`}
                </Text>
                <OutcomeBadge status={item.status} />
              </View>
              <Text className="text-sm text-neutral-500">
                {item.partner.display_name}
              </Text>
              {item.archived_at && (
                <Text className="text-xs text-neutral-400 mt-2">
                  Archived: {new Date(item.archived_at).toLocaleDateString()}
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
