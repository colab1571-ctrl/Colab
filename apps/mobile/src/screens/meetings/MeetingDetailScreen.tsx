/**
 * MeetingDetailScreen
 *
 * Shows meeting details: join link, status badge, artifacts (transcript/recording),
 * bot consent UI, countdown to meeting.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useNavigation, useRoute } from "@react-navigation/native";

interface Meeting {
  id: string;
  collab_id: string;
  organizer_profile_id: string;
  scheduled_at: string;
  duration_min: number;
  join_url: string;
  ics_url: string | null;
  status: "scheduled" | "started" | "ended" | "cancelled";
  bot_enabled: boolean;
  bot_status: "none" | "requested" | "joining" | "joined" | "left" | "failed";
  recall_bot_id: string | null;
  bot_consent: { participant_a: boolean; participant_b: boolean };
}

interface Artifact {
  id: string;
  kind: "transcript" | "recording" | "summary";
  download_url: string;
  ready_at: string;
}

const STATUS_LABELS: Record<Meeting["status"], string> = {
  scheduled: "Upcoming",
  started: "In Progress",
  ended: "Completed",
  cancelled: "Cancelled",
};

const STATUS_COLORS: Record<Meeting["status"], string> = {
  scheduled: "#6C63FF",
  started: "#22c55e",
  ended: "#94a3b8",
  cancelled: "#ef4444",
};

const BOT_STATUS_LABELS: Record<Meeting["bot_status"], string> = {
  none: "Not requested",
  requested: "Scheduled",
  joining: "Joining...",
  joined: "Recording",
  left: "Recording done",
  failed: "Bot failed",
};

export default function MeetingDetailScreen(): React.ReactElement {
  const navigation = useNavigation();
  const route = useRoute<any>();
  const { meetingId } = route.params as { meetingId: string };

  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [countdown, setCountdown] = useState<string>("");

  const loadMeeting = useCallback(async () => {
    try {
      const resp = await fetch(`/v1/meetings/${meetingId}`);
      if (!resp.ok) throw new Error("Failed to load meeting");
      const data: Meeting = await resp.json();
      setMeeting(data);
    } catch (err: any) {
      Alert.alert("Error", err.message);
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  const loadArtifacts = useCallback(async () => {
    try {
      const resp = await fetch(`/v1/meetings/${meetingId}/artifacts`);
      if (!resp.ok) return;
      const data = await resp.json();
      setArtifacts(data.items);
    } catch (_) {
      // non-fatal
    }
  }, [meetingId]);

  useEffect(() => {
    loadMeeting();
    loadArtifacts();
  }, [loadMeeting, loadArtifacts]);

  // Countdown timer
  useEffect(() => {
    if (!meeting || meeting.status !== "scheduled") return;

    const interval = setInterval(() => {
      const diff = new Date(meeting.scheduled_at).getTime() - Date.now();
      if (diff <= 0) {
        setCountdown("Starting now");
        clearInterval(interval);
        return;
      }
      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      if (days > 0) {
        setCountdown(`${days}d ${hours}h`);
      } else if (hours > 0) {
        setCountdown(`${hours}h ${mins}m`);
      } else {
        setCountdown(`${mins}m`);
      }
    }, 30000);

    // Initial
    const diff = new Date(meeting.scheduled_at).getTime() - Date.now();
    if (diff > 0) {
      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      setCountdown(days > 0 ? `${days}d ${hours}h` : hours > 0 ? `${hours}h ${mins}m` : `${mins}m`);
    }

    return () => clearInterval(interval);
  }, [meeting]);

  async function handleJoin(): Promise<void> {
    if (!meeting?.join_url) return;
    setJoining(true);
    try {
      const canOpen = await Linking.canOpenURL(meeting.join_url);
      if (canOpen) {
        await Linking.openURL(meeting.join_url);
      } else {
        Alert.alert("Cannot open link", "Install Google Meet or use a browser to join.");
      }
    } finally {
      setJoining(false);
    }
  }

  async function handleCancel(): Promise<void> {
    Alert.alert(
      "Cancel Meeting",
      "Are you sure you want to cancel this meeting?",
      [
        { text: "Keep", style: "cancel" },
        {
          text: "Cancel Meeting",
          style: "destructive",
          onPress: async () => {
            try {
              const resp = await fetch(`/v1/meetings/${meetingId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: "cancelled" }),
              });
              if (!resp.ok) throw new Error("Failed to cancel");
              await loadMeeting();
            } catch (err: any) {
              Alert.alert("Error", err.message);
            }
          },
        },
      ]
    );
  }

  async function handleDownloadIcs(): Promise<void> {
    if (!meeting?.ics_url) return;
    await Linking.openURL(meeting.ics_url);
  }

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#6C63FF" />
      </View>
    );
  }

  if (!meeting) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>Meeting not found.</Text>
      </View>
    );
  }

  const scheduledDate = new Date(meeting.scheduled_at);
  const isUpcoming = meeting.status === "scheduled";
  const isEnded = meeting.status === "ended";

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Status + Time */}
      <View style={styles.card}>
        <View
          style={[
            styles.statusBadge,
            { backgroundColor: STATUS_COLORS[meeting.status] + "22" },
          ]}
        >
          <Text
            style={[
              styles.statusText,
              { color: STATUS_COLORS[meeting.status] },
            ]}
          >
            {STATUS_LABELS[meeting.status]}
          </Text>
        </View>

        <Text style={styles.dateText}>
          {scheduledDate.toLocaleDateString(undefined, {
            weekday: "long",
            month: "long",
            day: "numeric",
            year: "numeric",
          })}
        </Text>
        <Text style={styles.timeText}>
          {scheduledDate.toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            timeZoneName: "short",
          })}
          {" "}·{" "}
          {meeting.duration_min < 60
            ? `${meeting.duration_min} min`
            : `${meeting.duration_min / 60} hr`}
        </Text>

        {isUpcoming && countdown ? (
          <Text style={styles.countdownText}>Starts in {countdown}</Text>
        ) : null}
      </View>

      {/* Join Button */}
      {meeting.status !== "cancelled" && (
        <Pressable
          style={[styles.joinButton, !isUpcoming && styles.joinButtonMuted]}
          onPress={handleJoin}
          disabled={joining}
        >
          {joining ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.joinButtonText}>Join Google Meet</Text>
          )}
        </Pressable>
      )}

      {/* Add to Calendar */}
      {meeting.ics_url && meeting.status !== "cancelled" && (
        <Pressable style={styles.icsButton} onPress={handleDownloadIcs}>
          <Text style={styles.icsButtonText}>Add to Calendar (.ics)</Text>
        </Pressable>
      )}

      {/* Bot Status */}
      {meeting.bot_enabled && (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Recording Bot</Text>
          <Text style={styles.botStatusText}>
            Status: {BOT_STATUS_LABELS[meeting.bot_status]}
          </Text>
          <View style={styles.consentRow}>
            <Text style={styles.consentItem}>
              {meeting.bot_consent.participant_a ? "Participant A: Approved" : "Participant A: Pending"}
            </Text>
            <Text style={styles.consentItem}>
              {meeting.bot_consent.participant_b ? "Participant B: Approved" : "Participant B: Pending"}
            </Text>
          </View>
          {meeting.bot_status === "failed" && (
            <Text style={styles.botErrorText}>
              The recording bot encountered an error and could not join.
            </Text>
          )}
        </View>
      )}

      {/* Artifacts */}
      {isEnded && artifacts.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Recording & Transcript</Text>
          {artifacts.map((artifact) => (
            <Pressable
              key={artifact.id}
              style={styles.artifactRow}
              onPress={() => Linking.openURL(artifact.download_url)}
            >
              <Text style={styles.artifactKind}>
                {artifact.kind.charAt(0).toUpperCase() + artifact.kind.slice(1)}
              </Text>
              <Text style={styles.artifactDownload}>Download</Text>
            </Pressable>
          ))}
        </View>
      )}

      {/* Cancel */}
      {isUpcoming && (
        <Pressable style={styles.cancelButton} onPress={handleCancel}>
          <Text style={styles.cancelButtonText}>Cancel Meeting</Text>
        </Pressable>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8f8ff" },
  content: { padding: 20, gap: 16 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center" },
  card: {
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 20,
    shadowColor: "#6C63FF",
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
  },
  statusBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 20,
    marginBottom: 12,
  },
  statusText: { fontSize: 12, fontWeight: "700", textTransform: "uppercase" },
  dateText: { fontSize: 18, fontWeight: "700", color: "#1a1a2e", marginBottom: 4 },
  timeText: { fontSize: 15, color: "#4a4a6a" },
  countdownText: { fontSize: 13, color: "#6C63FF", marginTop: 8, fontWeight: "600" },
  joinButton: {
    backgroundColor: "#6C63FF",
    borderRadius: 14,
    padding: 18,
    alignItems: "center",
  },
  joinButtonMuted: { backgroundColor: "#9d97e8" },
  joinButtonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  icsButton: {
    borderWidth: 1,
    borderColor: "#6C63FF",
    borderRadius: 14,
    padding: 14,
    alignItems: "center",
  },
  icsButtonText: { color: "#6C63FF", fontSize: 14, fontWeight: "600" },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: "#1a1a2e", marginBottom: 12 },
  botStatusText: { fontSize: 14, color: "#4a4a6a", marginBottom: 8 },
  consentRow: { gap: 4 },
  consentItem: { fontSize: 13, color: "#6b6b8a" },
  botErrorText: { fontSize: 13, color: "#ef4444", marginTop: 8 },
  artifactRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#f0f0f8",
  },
  artifactKind: { fontSize: 15, color: "#1a1a2e", fontWeight: "600" },
  artifactDownload: { fontSize: 14, color: "#6C63FF", fontWeight: "600" },
  cancelButton: { padding: 16, alignItems: "center" },
  cancelButtonText: { color: "#ef4444", fontSize: 14, fontWeight: "600" },
  errorText: { color: "#ef4444", fontSize: 16 },
});
