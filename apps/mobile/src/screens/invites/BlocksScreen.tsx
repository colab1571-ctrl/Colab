/**
 * BlocksScreen — Manage blocked users list.
 *
 * Shows profiles the current user has blocked. Allows unblocking.
 * Blocked status is private — blocked users have no knowledge of the block.
 *
 * Spec §6.2: Only the blocker can remove the block.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  RefreshControl,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { getBlocks, unblockProfile } from "../../api/invites";

type BlockCard = {
  profile_id: string;
  display_name: string | null;
  avatar_url: string | null;
  blocked_at: string;
};

type Props = object;

export function BlocksScreen(_props: Props): React.ReactElement {
  const [blocks, setBlocks] = useState<BlockCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [unblockingId, setUnblockingId] = useState<string | null>(null);

  const loadBlocks = useCallback(
    async (reset = false) => {
      if (loading && !reset) return;
      setLoading(true);
      try {
        const result = await getBlocks({
          cursor: reset ? undefined : cursor ?? undefined,
          limit: 50,
        });
        if (reset) {
          setBlocks(result.items);
        } else {
          setBlocks((prev) => [...prev, ...result.items]);
        }
        setCursor(result.next_cursor ?? null);
        setHasMore(!!result.next_cursor);
      } catch (err) {
        console.error("Failed to load blocks:", err);
      } finally {
        setLoading(false);
      }
    },
    [cursor, loading]
  );

  useEffect(() => {
    loadBlocks(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setBlocks([]);
    setCursor(null);
    await loadBlocks(true);
    setRefreshing(false);
  }, [loadBlocks]);

  const handleUnblock = useCallback((profileId: string, displayName: string | null) => {
    Alert.alert(
      "Unblock",
      `Unblock ${displayName ?? "this user"}? They will be able to see your profile again.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Unblock",
          style: "destructive",
          onPress: async () => {
            setUnblockingId(profileId);
            try {
              await unblockProfile(profileId);
              setBlocks((prev) => prev.filter((b) => b.profile_id !== profileId));
            } catch (err) {
              console.error("Unblock failed:", err);
              Alert.alert("Error", "Failed to unblock. Please try again.");
            } finally {
              setUnblockingId(null);
            }
          },
        },
      ]
    );
  }, []);

  const renderBlock = useCallback(
    ({ item }: { item: BlockCard }) => {
      const isUnblocking = unblockingId === item.profile_id;
      const blockedDate = new Date(item.blocked_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });

      return (
        <View
          className="flex-row items-center bg-white px-4 py-3 border-b border-neutral-100"
          testID={`block-item-${item.profile_id}`}
        >
          {item.avatar_url ? (
            <Image
              source={{ uri: item.avatar_url }}
              className="w-10 h-10 rounded-full mr-3"
            />
          ) : (
            <View className="w-10 h-10 rounded-full bg-neutral-200 mr-3 items-center justify-center">
              <Text className="text-neutral-500 text-base font-bold">
                {item.display_name?.[0]?.toUpperCase() ?? "?"}
              </Text>
            </View>
          )}
          <View className="flex-1">
            <Text className="text-base font-medium text-neutral-900">
              {item.display_name ?? "Unknown"}
            </Text>
            <Text className="text-xs text-neutral-400">Blocked {blockedDate}</Text>
          </View>
          <TouchableOpacity
            className="bg-neutral-100 px-3 py-2 rounded-lg"
            onPress={() => handleUnblock(item.profile_id, item.display_name)}
            disabled={isUnblocking}
            testID={`unblock-btn-${item.profile_id}`}
          >
            {isUnblocking ? (
              <ActivityIndicator size="small" />
            ) : (
              <Text className="text-sm font-medium text-neutral-600">Unblock</Text>
            )}
          </TouchableOpacity>
        </View>
      );
    },
    [handleUnblock, unblockingId]
  );

  return (
    <View className="flex-1 bg-white">
      <View className="px-4 py-3 bg-neutral-50 border-b border-neutral-100">
        <Text className="text-sm text-neutral-500">
          {blocks.length} {blocks.length === 1 ? "person" : "people"} blocked.
          Blocked users cannot see your profile or contact you.
        </Text>
      </View>

      <FlatList
        data={blocks}
        keyExtractor={(item) => item.profile_id}
        renderItem={renderBlock}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
        onEndReached={() => {
          if (hasMore && !loading) loadBlocks();
        }}
        onEndReachedThreshold={0.3}
        ListEmptyComponent={
          !loading ? (
            <View className="items-center justify-center py-20">
              <Text className="text-4xl mb-3">🛡️</Text>
              <Text className="text-neutral-500 text-base font-medium">No blocked users</Text>
              <Text className="text-neutral-400 text-sm mt-1 text-center px-8">
                Blocked users appear here. You can always unblock them later.
              </Text>
            </View>
          ) : null
        }
        ListFooterComponent={loading && blocks.length > 0 ? <ActivityIndicator className="py-4" /> : null}
      />
    </View>
  );
}
