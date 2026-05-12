import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useNavigation, useRoute } from "@react-navigation/native";

interface Participant {
  profile_id: string;
  display_name: string;
  avatar_url: string | null;
}

interface StatusEvent {
  id: string;
  prev_status: string;
  new_status: string;
  actor_profile_id: string;
  note: string | null;
  created_at: string;
}

interface FeedbackRecord {
  id: string;
  from_profile_id: string;
  target: "project" | "partner";
  rating: "up" | "down";
  tags: string[];
  comment: string | null;
}

interface CollabDetail {
  id: string;
  title: string | null;
  description: string | null;
  status: string;
  is_read_only: boolean;
  last_activity_at: string;
  archived_at: string | null;
  completed_at: string | null;
  participants: Participant[];
  status_history: StatusEvent[];
  feedback: FeedbackRecord[];
}

const STATUS_OPTIONS = [
  { value: "still_deciding", label: "Still Deciding" },
  { value: "in_progress", label: "In Progress" },
  { value: "completed", label: "Completed" },
  { value: "didnt_work_out", label: "Didn't Work Out" },
];

function statusLabel(s: string): string {
  return STATUS_OPTIONS.find((o) => o.value === s)?.label ?? s;
}

function isTerminal(status: string): boolean {
  return status === "completed" || status === "didnt_work_out";
}

export function CollabDetailScreen(): React.ReactElement {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { collabId } = route.params as { collabId: string };

  const [collab, setCollab] = useState<CollabDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [transitionLoading, setTransitionLoading] = useState(false);
  const [showFeedbackPrompt, setShowFeedbackPrompt] = useState(false);
  const [currentProfileId, setCurrentProfileId] = useState<string | null>(null);

  const fetchCollab = useCallback(async () => {
    try {
      const resp = await fetch(`/collabs/${collabId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: CollabDetail = await resp.json();
      setCollab(data);
    } catch (e) {
      Alert.alert("Error", (e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [collabId]);

  useEffect(() => {
    fetchCollab();
  }, [fetchCollab]);

  useEffect(() => {
    if (collab && isTerminal(collab.status)) {
      // Show feedback prompt if current user hasn't submitted for both targets
      setShowFeedbackPrompt(true);
    }
  }, [collab]);

  const handleStatusTransition = useCallback(
    async (newStatus: string) => {
      if (!collab) return;
      setTransitionLoading(true);
      try {
        const resp = await fetch(`/collabs/${collabId}/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_status: newStatus }),
        });
        if (resp.status === 409) {
          const err = await resp.json();
          Alert.alert("Cannot Change Status", err.message ?? "Invalid transition");
          return;
        }
        if (!resp.ok) {
          const err = await resp.json();
          Alert.alert("Error", err.detail?.error_code ?? "Failed to update status");
          return;
        }
        await fetchCollab();
      } catch (e) {
        Alert.alert("Error", (e as Error).message);
      } finally {
        setTransitionLoading(false);
      }
    },
    [collab, collabId, fetchCollab]
  );

  const handleExportRequest = useCallback(async () => {
    try {
      const resp = await fetch(`/collabs/${collabId}/export`, { method: "POST" });
      if (resp.status === 403) {
        const err = await resp.json();
        if (err.detail?.error_code === "EXPORT_REQUIRES_PREMIUM") {
          Alert.alert(
            "Premium Required",
            "Chat export is a Premium feature. Upgrade to download your conversation."
          );
          return;
        }
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      navigation.navigate("ExportStatus", { exportId: data.export_id });
    } catch (e) {
      Alert.alert("Error", (e as Error).message);
    }
  }, [collabId, navigation]);

  if (loading) {
    return (
      <View className="flex-1 bg-white items-center justify-center">
        <ActivityIndicator size="large" color="#4f46e5" />
      </View>
    );
  }

  if (!collab) {
    return (
      <View className="flex-1 bg-white items-center justify-center">
        <Text className="text-neutral-400">Collaboration not found.</Text>
      </View>
    );
  }

  const terminal = isTerminal(collab.status);
  const readOnly = collab.is_read_only || !!collab.archived_at;

  return (
    <ScrollView className="flex-1 bg-neutral-50">
      {/* Header */}
      <View className="bg-white px-4 pt-6 pb-4">
        <Text className="text-xl font-bold text-neutral-900">
          {collab.title ?? `Collab with ${collab.participants.find((p) => p.profile_id !== currentProfileId)?.display_name ?? "Partner"}`}
        </Text>
        {collab.description && (
          <Text className="text-sm text-neutral-500 mt-1">{collab.description}</Text>
        )}

        {/* Status badge */}
        <View className="flex-row items-center mt-3 gap-2">
          <View className="bg-indigo-50 px-3 py-1 rounded-full">
            <Text className="text-indigo-700 text-sm font-medium">
              {statusLabel(collab.status)}
            </Text>
          </View>
          {readOnly && (
            <View className="bg-orange-50 px-3 py-1 rounded-full">
              <Text className="text-orange-600 text-sm">Read-only</Text>
            </View>
          )}
          {collab.archived_at && (
            <View className="bg-neutral-100 px-3 py-1 rounded-full">
              <Text className="text-neutral-500 text-sm">Archived</Text>
            </View>
          )}
        </View>
      </View>

      {/* Status transition actions */}
      {!readOnly && !terminal && (
        <View className="bg-white mx-4 mt-4 rounded-2xl shadow-sm p-4">
          <Text className="text-sm font-semibold text-neutral-700 mb-3">
            Update Status
          </Text>
          {transitionLoading ? (
            <ActivityIndicator color="#4f46e5" />
          ) : (
            <View className="gap-2">
              {["still_deciding", "in_progress", "completed", "didnt_work_out"]
                .filter((s) => s !== collab.status)
                .map((s) => (
                  <Pressable
                    key={s}
                    onPress={() => handleStatusTransition(s)}
                    className="border border-indigo-200 rounded-xl py-2 px-3 items-center"
                  >
                    <Text className="text-indigo-700 font-medium text-sm">
                      Mark as {statusLabel(s)}
                    </Text>
                  </Pressable>
                ))}
            </View>
          )}
        </View>
      )}

      {/* Feedback prompt (post-terminal) */}
      {showFeedbackPrompt && terminal && (
        <Pressable
          onPress={() =>
            navigation.navigate("FeedbackPrompt", { collabId: collab.id })
          }
          className="bg-indigo-600 mx-4 mt-4 rounded-2xl p-4"
        >
          <Text className="text-white font-semibold text-base">
            Share Your Feedback
          </Text>
          <Text className="text-indigo-200 text-sm mt-1">
            Rate the project and your partner experience.
          </Text>
        </Pressable>
      )}

      {/* Export */}
      <Pressable
        onPress={handleExportRequest}
        className="bg-white mx-4 mt-4 rounded-2xl shadow-sm p-4 flex-row items-center justify-between"
      >
        <View>
          <Text className="text-sm font-semibold text-neutral-800">
            Export Chat
          </Text>
          <Text className="text-xs text-neutral-400 mt-0.5">
            PDF transcript + media (Premium)
          </Text>
        </View>
        <Text className="text-indigo-600 font-semibold">Export</Text>
      </Pressable>

      {/* Status history */}
      {collab.status_history.length > 0 && (
        <View className="bg-white mx-4 mt-4 rounded-2xl shadow-sm p-4">
          <Text className="text-sm font-semibold text-neutral-700 mb-3">
            Status History
          </Text>
          {collab.status_history.map((ev) => (
            <View key={ev.id} className="mb-2 pb-2 border-b border-neutral-100 last:border-b-0">
              <Text className="text-sm text-neutral-700">
                {statusLabel(ev.prev_status)} → {statusLabel(ev.new_status)}
              </Text>
              <Text className="text-xs text-neutral-400">
                {new Date(ev.created_at).toLocaleString()}
              </Text>
              {ev.note && (
                <Text className="text-xs text-neutral-500 mt-0.5 italic">
                  "{ev.note}"
                </Text>
              )}
            </View>
          ))}
        </View>
      )}

      <View className="h-8" />
    </ScrollView>
  );
}
