/**
 * ScheduleMeetingModal
 *
 * Allows a collab participant to schedule a Google Meet call.
 * Fields: date + time picker, duration selector, bot consent toggle.
 * Validates future scheduling; submits to POST /v1/collabs/{collab_id}/meetings.
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import DateTimePicker, {
  DateTimePickerEvent,
} from "@react-native-community/datetimepicker";

interface Props {
  visible: boolean;
  collabId: string;
  onClose: () => void;
  onScheduled: (meeting: MeetingOut) => void;
}

interface MeetingOut {
  id: string;
  join_url: string;
  scheduled_at: string;
  duration_min: number;
  bot_enabled: boolean;
  bot_status: string;
  ics_url: string | null;
  status: string;
}

const DURATION_OPTIONS = [15, 30, 45, 60, 90, 120];

export default function ScheduleMeetingModal({
  visible,
  collabId,
  onClose,
  onScheduled,
}: Props): React.ReactElement {
  const [scheduledAt, setScheduledAt] = useState<Date>(() => {
    const d = new Date();
    d.setHours(d.getHours() + 1, 0, 0, 0);
    return d;
  });
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [durationMin, setDurationMin] = useState(60);
  const [botEnabled, setBotEnabled] = useState(false);
  const [loading, setLoading] = useState(false);

  function handleDateChange(
    _event: DateTimePickerEvent,
    date?: Date
  ): void {
    setShowDatePicker(false);
    if (date) {
      const updated = new Date(scheduledAt);
      updated.setFullYear(date.getFullYear(), date.getMonth(), date.getDate());
      setScheduledAt(updated);
    }
  }

  function handleTimeChange(
    _event: DateTimePickerEvent,
    time?: Date
  ): void {
    setShowTimePicker(false);
    if (time) {
      const updated = new Date(scheduledAt);
      updated.setHours(time.getHours(), time.getMinutes(), 0, 0);
      setScheduledAt(updated);
    }
  }

  function formatDate(date: Date): string {
    return date.toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  function formatTime(date: Date): string {
    return date.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
  }

  async function handleSubmit(): Promise<void> {
    const now = new Date();
    if (scheduledAt <= now) {
      Alert.alert("Invalid Time", "Please choose a future date and time.");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `/v1/collabs/${collabId}/meetings`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scheduled_at: scheduledAt.toISOString(),
            duration_min: durationMin,
            bot_enabled: botEnabled,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        if (response.status === 409) {
          Alert.alert(
            "Scheduling Conflict",
            "There is already a meeting scheduled at this time. Please choose a different time."
          );
          return;
        }
        throw new Error(error.detail || "Failed to schedule meeting");
      }

      const meeting: MeetingOut = await response.json();
      onScheduled(meeting);
      onClose();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Could not schedule meeting. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <Text style={styles.title}>Schedule Meeting</Text>
          <Pressable onPress={onClose} style={styles.closeButton}>
            <Text style={styles.closeButtonText}>Cancel</Text>
          </Pressable>
        </View>

        {/* Date Picker */}
        <View style={styles.section}>
          <Text style={styles.label}>Date</Text>
          <Pressable
            style={styles.pickerButton}
            onPress={() => setShowDatePicker(true)}
          >
            <Text style={styles.pickerButtonText}>{formatDate(scheduledAt)}</Text>
          </Pressable>
          {showDatePicker && (
            <DateTimePicker
              value={scheduledAt}
              mode="date"
              display="calendar"
              minimumDate={new Date()}
              onChange={handleDateChange}
            />
          )}
        </View>

        {/* Time Picker */}
        <View style={styles.section}>
          <Text style={styles.label}>Time</Text>
          <Pressable
            style={styles.pickerButton}
            onPress={() => setShowTimePicker(true)}
          >
            <Text style={styles.pickerButtonText}>{formatTime(scheduledAt)}</Text>
          </Pressable>
          {showTimePicker && (
            <DateTimePicker
              value={scheduledAt}
              mode="time"
              display="spinner"
              minuteInterval={15}
              onChange={handleTimeChange}
            />
          )}
        </View>

        {/* Duration Selector */}
        <View style={styles.section}>
          <Text style={styles.label}>Duration</Text>
          <View style={styles.durationRow}>
            {DURATION_OPTIONS.map((min) => (
              <Pressable
                key={min}
                style={[
                  styles.durationChip,
                  durationMin === min && styles.durationChipSelected,
                ]}
                onPress={() => setDurationMin(min)}
              >
                <Text
                  style={[
                    styles.durationChipText,
                    durationMin === min && styles.durationChipTextSelected,
                  ]}
                >
                  {min < 60 ? `${min}m` : `${min / 60}h`}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* Bot Consent Toggle */}
        <View style={styles.section}>
          <View style={styles.toggleRow}>
            <View style={styles.toggleInfo}>
              <Text style={styles.label}>Enable Recording Bot</Text>
              <Text style={styles.toggleSubtext}>
                A Recall.ai bot will join to record and transcribe your meeting.
                Both participants must approve before the bot joins.
              </Text>
            </View>
            <Switch
              value={botEnabled}
              onValueChange={setBotEnabled}
              trackColor={{ false: "#767577", true: "#6C63FF" }}
              thumbColor={botEnabled ? "#fff" : "#f4f3f4"}
            />
          </View>
        </View>

        {/* Submit Button */}
        <Pressable
          style={[styles.submitButton, loading && styles.submitButtonDisabled]}
          onPress={handleSubmit}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.submitButtonText}>Schedule Meeting</Text>
          )}
        </Pressable>
      </ScrollView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
  },
  content: {
    padding: 24,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 24,
  },
  title: {
    fontSize: 20,
    fontWeight: "700",
    color: "#1a1a2e",
  },
  closeButton: {
    padding: 8,
  },
  closeButtonText: {
    fontSize: 16,
    color: "#6C63FF",
  },
  section: {
    marginBottom: 24,
  },
  label: {
    fontSize: 14,
    fontWeight: "600",
    color: "#4a4a6a",
    marginBottom: 8,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  pickerButton: {
    borderWidth: 1,
    borderColor: "#e0e0f0",
    borderRadius: 12,
    padding: 16,
    backgroundColor: "#f8f8ff",
  },
  pickerButtonText: {
    fontSize: 16,
    color: "#1a1a2e",
  },
  durationRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  durationChip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#e0e0f0",
    backgroundColor: "#f8f8ff",
  },
  durationChipSelected: {
    backgroundColor: "#6C63FF",
    borderColor: "#6C63FF",
  },
  durationChipText: {
    fontSize: 14,
    color: "#4a4a6a",
    fontWeight: "500",
  },
  durationChipTextSelected: {
    color: "#fff",
    fontWeight: "700",
  },
  toggleRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 16,
  },
  toggleInfo: {
    flex: 1,
  },
  toggleSubtext: {
    fontSize: 13,
    color: "#6b6b8a",
    lineHeight: 18,
  },
  submitButton: {
    backgroundColor: "#6C63FF",
    borderRadius: 14,
    padding: 18,
    alignItems: "center",
    marginTop: 8,
  },
  submitButtonDisabled: {
    opacity: 0.6,
  },
  submitButtonText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
});
