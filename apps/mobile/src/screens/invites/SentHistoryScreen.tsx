/**
 * SentHistoryScreen — Sent Vibe Check history with status filter.
 *
 * Shows sender's invite history. Terminal statuses (rejected/expired/cancelled)
 * are visible only here (Journey G history) — they're silent from the sender's
 * perspective in real-time but visible in the sent history view.
 *
 * FR-B-10: 30-day TTL → status flips to expired in sender's "past sent" history.
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
import { cancelInvite, getSentInvites } from "../../api/invites";

type SentStatus = "pending" | "accepted" | "rejected" | "expired" | "cancelled" | "all";

type InviteCard = {
  invite_id: string;
  to_profile: {
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

const STATUS_TABS: { label: string; value: SentStatus }[] = [
  { label: "Pending", value: "pending" },
  { label: "Accepted", value: "accepted" },
  { label: "History", value: "all" },
];

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  pending: { label: "Pending", color: "bg-amber-100 text-amber-700" },
  accepted: { label: "Accepted", color: "bg-green-100 text-green-700" },
  rejected: { label: "Passed", color: "bg-neutral-100 text-neutral-500" },
  expired: { label: "Expired", color: "bg-neutral-100 text-neutral-400" },
  cancelled: { label: "Cancelled", color: "bg-red-50 text-red-400" },
};

export function SentHistoryScreen({ navigation }: Props): React.ReactElement {
  const [activeStatus, setActiveStatus] = useState<SentStatus>("pending");
  const [invites, setInvites] = useState<InviteCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const loadInvites = useCallback(
    async (reset = false) => {
      if (loading && !reset) return;
      setLoading(true);
      try {
        const result = await getSentInvites({
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
        console.error("Failed to load sent invites:", err);
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
    await loadInvites(true);
    setRefreshing(false);
  }, [loadInvites]);

  const handleCancel = useCallback(async (inviteId: string) => {
    setCancellingId(inviteId);
    try {
      await cancelInvite(inviteId);
      setInvites((prev) =>
        prev.map((i) =>
          i.invite_id === inviteId ? { ...i, status: "cancelled" } : i
        )
      );
    } catch (err) {
      console.error("Cancel failed:", err);
    } finally {
      setCancellingId(null);
    }
  }, []);

  const renderInvite = useCallback(
    ({ item }: { item: InviteCard }) => {
      const profile = item.to_profile;
      const badge = STATUS_BADGE[item.status] ?? { label: item.status, color: "bg-neutral-100 text-neutral-500" };
      const isCancelling = cancellingId === item.invite_id;

      return (
        <View
          className="bg-white border border-neutral-100 rounded-2xl p-4 mb-3 mx-4 shadow-sm"
          testID={`sent-invite-${item.invite_id}`}
        >
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
            <View className={`rounded-full px-3 py-1 ${badge.color}`}>
              <Text className="text-xs font-medium">{badge.label}</Text>
            </View>
          </View>

          <Text className="text-sm text-neutral-600 mb-3 leading-5 italic">
            "{item.synopsis}"
          </Text>

          {item.status === "pending" && (
            <TouchableOpacity
              className="bg-neutral-100 py-2 rounded-xl items-center"
              onPress={() => handleCancel(item.invite_id)}
              disabled={isCancelling}
              testID={`cancel-btn-${item.invite_id}`}
            >
              {isCancelling ? (
                <ActivityIndicator />
              ) : (
                <Text className="text-neutral-500 text-sm font-medium">Cancel Invite</Text>
              )}
            </TouchableOpacity>
          )}

          {item.status === "accepted" && (
            <TouchableOpacity
              className="bg-brand-primary/10 py-2 rounded-xl items-center"
              onPress={() =>
                navigation.navigate("Chat", {
                  profileId: profile?.profile_id,
                  displayName: profile?.display_name,
                })
              }
            >
              <Text className="text-brand-primary text-sm font-semibold">Open Chat</Text>
            </TouchableOpacity>
          )}

          {item.status === "expired" && (
            <Text className="text-xs text-neutral-400 text-center">
              Expired after 30 days
            </Text>
          )}
        </View>
      );
    },
    [cancellingId, handleCancel, navigation]
  );

  return (
    <View className="flex-1 bg-neutral-50">
      <View className="flex-row px-4 pt-4 pb-2 bg-white border-b border-neutral-100">
        {STATUS_TABS.map((tab) => (
          <TouchableOpacity
            key={tab.value}
            className={`flex-1 py-2 rounded-lg items-center mx-1 ${
              activeStatus === tab.value ? "bg-brand-primary" : "bg-neutral-100"
            }`}
            onPress={() => setActiveStatus(tab.value)}
            testID={`sent-tab-${tab.value}`}
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
          if (hasMore && !loading) loadInvites();
        }}
        onEndReachedThreshold={0.3}
        ListEmptyComponent={
          !loading ? (
            <View className="items-center justify-center py-16">
              <Text className="text-4xl mb-3">📤</Text>
              <Text className="text-neutral-500 text-base font-medium">
                No sent Vibe Checks
              </Text>
              <Text className="text-neutral-400 text-sm mt-1">
                Find someone to collaborate with!
              </Text>
            </View>
          ) : null
        }
        ListFooterComponent={loading && invites.length > 0 ? <ActivityIndicator className="py-4" /> : null}
      />
    </View>
  );
}
