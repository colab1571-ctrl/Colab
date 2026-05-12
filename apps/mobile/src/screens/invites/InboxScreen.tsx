/**
 * InboxScreen — Received Vibe Check invites.
 *
 * Features:
 *   - Lists pending invites by default; status filter tabs
 *   - Accept → opens chat + shows Match! celebration if mutual
 *   - Reject → silent (invite disappears from pending, no banner to sender)
 *   - Cursor-based infinite scroll
 *
 * FR-B-9: Accept / reject from inbox.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  RefreshControl,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { getInviteInbox, respondToInvite } from "../../api/invites";

type Status = "pending" | "accepted" | "all";

type InviteCard = {
  invite_id: string;
  from_profile: {
    profile_id: string;
    display_name: string | null;
    avatar_url: string | null;
    city: string | null;
    top_vocation: string | null;
  } | null;
  synopsis: string;
  status: string;
  created_at: string;
  archive_at: string;
  ai_match_score: number | null;
};

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const STATUS_TABS: { label: string; value: Status }[] = [
  { label: "Pending", value: "pending" },
  { label: "Accepted", value: "accepted" },
  { label: "All", value: "all" },
];

export function InboxScreen({ navigation }: Props): React.ReactElement {
  const [activeStatus, setActiveStatus] = useState<Status>("pending");
  const [invites, setInvites] = useState<InviteCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [respondingId, setRespondingId] = useState<string | null>(null);

  const loadInvites = useCallback(
    async (reset = false) => {
      if (loading && !reset) return;
      setLoading(true);
      try {
        const result = await getInviteInbox({
          status: activeStatus,
          cursor: reset ? undefined : cursor ?? undefined,
          limit: 20,
        });
        if (reset) {
          setInvites(result.items);
        } else {
          setInvites((prev) => [...prev, ...result.items]);
        }
        setCursor(result.next_cursor ?? null);
        setHasMore(!!result.next_cursor);
      } catch (err) {
        console.error("Failed to load inbox:", err);
      } finally {
        setLoading(false);
      }
    },
    [activeStatus, cursor, loading]
  );

  useEffect(() => {
    setInvites([]);
    setCursor(null);
    setHasMore(true);
    loadInvites(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStatus]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setInvites([]);
    setCursor(null);
    setHasMore(true);
    await loadInvites(true);
    setRefreshing(false);
  }, [loadInvites]);

  const handleAccept = useCallback(
    async (invite: InviteCard) => {
      setRespondingId(invite.invite_id);
      try {
        const result = await respondToInvite(invite.invite_id, "accept");
        // Remove from pending list
        setInvites((prev) => prev.filter((i) => i.invite_id !== invite.invite_id));

        if (result.matched) {
          // Navigate to match celebration screen
          navigation.navigate("MatchCelebration", {
            profileId: invite.from_profile?.profile_id,
            displayName: invite.from_profile?.display_name,
          });
        }
      } catch (err) {
        console.error("Accept failed:", err);
      } finally {
        setRespondingId(null);
      }
    },
    [navigation]
  );

  const handleReject = useCallback(async (inviteId: string) => {
    setRespondingId(inviteId);
    try {
      await respondToInvite(inviteId, "reject");
      // Silent — remove from inbox without any notification to sender
      setInvites((prev) => prev.filter((i) => i.invite_id !== inviteId));
    } catch (err) {
      console.error("Reject failed:", err);
    } finally {
      setRespondingId(null);
    }
  }, []);

  const renderInvite = useCallback(
    ({ item }: { item: InviteCard }) => {
      const isResponding = respondingId === item.invite_id;
      const profile = item.from_profile;

      return (
        <View
          className="bg-white border border-neutral-100 rounded-2xl p-4 mb-3 mx-4 shadow-sm"
          testID={`invite-card-${item.invite_id}`}
        >
          {/* Profile info */}
          <View className="flex-row items-center mb-3">
            {profile?.avatar_url ? (
              <Image
                source={{ uri: profile.avatar_url }}
                className="w-12 h-12 rounded-full mr-3"
              />
            ) : (
              <View className="w-12 h-12 rounded-full bg-neutral-200 mr-3 items-center justify-center">
                <Text className="text-neutral-500 text-lg font-bold">
                  {profile?.display_name?.[0]?.toUpperCase() ?? "?"}
                </Text>
              </View>
            )}
            <View className="flex-1">
              <Text className="text-base font-bold text-neutral-900">
                {profile?.display_name ?? "Unknown"}
              </Text>
              <Text className="text-sm text-neutral-500">
                {[profile?.top_vocation, profile?.city].filter(Boolean).join(" · ")}
              </Text>
            </View>
            {item.ai_match_score != null && (
              <View className="bg-brand-primary/10 rounded-full px-2 py-1">
                <Text className="text-xs font-bold text-brand-primary">
                  {Math.round(item.ai_match_score * 100)}% match
                </Text>
              </View>
            )}
          </View>

          {/* Synopsis */}
          <Text className="text-sm text-neutral-700 mb-4 leading-5">{item.synopsis}</Text>

          {/* Actions (only for pending) */}
          {item.status === "pending" && (
            <View className="flex-row gap-3">
              <TouchableOpacity
                className="flex-1 bg-brand-primary py-3 rounded-xl items-center"
                onPress={() => handleAccept(item)}
                disabled={isResponding}
                testID={`accept-btn-${item.invite_id}`}
              >
                {isResponding ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text className="text-white font-semibold text-sm">Accept</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity
                className="flex-1 bg-neutral-100 py-3 rounded-xl items-center"
                onPress={() => handleReject(item.invite_id)}
                disabled={isResponding}
                testID={`reject-btn-${item.invite_id}`}
              >
                <Text className="text-neutral-600 font-semibold text-sm">Pass</Text>
              </TouchableOpacity>
            </View>
          )}

          {item.status === "accepted" && (
            <View className="bg-green-50 rounded-xl py-2 px-4">
              <Text className="text-green-700 text-sm font-medium text-center">Accepted</Text>
            </View>
          )}
        </View>
      );
    },
    [handleAccept, handleReject, respondingId]
  );

  return (
    <View className="flex-1 bg-neutral-50">
      {/* Status filter tabs */}
      <View className="flex-row px-4 pt-4 pb-2 bg-white border-b border-neutral-100">
        {STATUS_TABS.map((tab) => (
          <TouchableOpacity
            key={tab.value}
            className={`flex-1 py-2 rounded-lg items-center mx-1 ${
              activeStatus === tab.value ? "bg-brand-primary" : "bg-neutral-100"
            }`}
            onPress={() => setActiveStatus(tab.value)}
            testID={`tab-${tab.value}`}
          >
            <Text
              className={`text-sm font-medium ${
                activeStatus === tab.value ? "text-white" : "text-neutral-500"
              }`}
            >
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <FlatList
        data={invites}
        keyExtractor={(item) => item.invite_id}
        renderItem={renderInvite}
        contentContainerStyle={{ paddingTop: 16, paddingBottom: 32 }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
        onEndReached={() => {
          if (hasMore && !loading) {
            loadInvites();
          }
        }}
        onEndReachedThreshold={0.3}
        ListEmptyComponent={
          !loading ? (
            <View className="flex-1 items-center justify-center py-16">
              <Text className="text-4xl mb-3">📭</Text>
              <Text className="text-neutral-500 text-base font-medium">No invites here</Text>
              <Text className="text-neutral-400 text-sm mt-1">
                {activeStatus === "pending"
                  ? "Pending Vibe Checks will appear here"
                  : "Nothing to show yet"}
              </Text>
            </View>
          ) : null
        }
        ListFooterComponent={
          loading && invites.length > 0 ? (
            <ActivityIndicator className="py-4" />
          ) : null
        }
      />
    </View>
  );
}
