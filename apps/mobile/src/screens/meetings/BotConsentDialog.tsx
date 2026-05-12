/**
 * BotConsentDialog
 *
 * Modal dialog asking a participant to allow or revoke Recall.ai bot access.
 * Both participants must tap "Allow" before the bot is dispatched.
 *
 * Props:
 * - meetingId: string
 * - botStatus: Meeting["bot_status"]
 * - myConsent: boolean   — has this participant already consented?
 * - otherParticipantName: string
 * - otherConsented: boolean
 * - onConsentChange: () => void — reload parent after consent change
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

type BotStatus = "none" | "requested" | "joining" | "joined" | "left" | "failed";

interface Props {
  visible: boolean;
  meetingId: string;
  botStatus: BotStatus;
  myConsent: boolean;
  otherParticipantName: string;
  otherConsented: boolean;
  onClose: () => void;
  onConsentChange: () => void;
}

const BOT_DISPATCHED_STATUSES: BotStatus[] = ["joining", "joined", "left", "failed"];

export default function BotConsentDialog({
  visible,
  meetingId,
  botStatus,
  myConsent,
  otherParticipantName,
  otherConsented,
  onClose,
  onConsentChange,
}: Props): React.ReactElement {
  const [loading, setLoading] = useState(false);

  const isDispatched = BOT_DISPATCHED_STATUSES.includes(botStatus);

  async function handleAllow(): Promise<void> {
    setLoading(true);
    try {
      const resp = await fetch(`/v1/meetings/${meetingId}/bot/consent`, {
        method: "POST",
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Failed to give consent");
      }
      const data = await resp.json();
      onConsentChange();

      if (data.both_consented) {
        Alert.alert(
          "Recording Approved",
          "Both participants have approved. The Recall.ai bot will join at the start of your meeting."
        );
      }
    } catch (err: any) {
      Alert.alert("Error", err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRevoke(): Promise<void> {
    if (isDispatched) {
      Alert.alert(
        "Cannot Revoke",
        "The bot has already been dispatched and cannot be recalled at this stage."
      );
      return;
    }

    Alert.alert(
      "Revoke Recording Consent",
      "Are you sure? The bot will not join if consent is revoked.",
      [
        { text: "Keep Consent", style: "cancel" },
        {
          text: "Revoke",
          style: "destructive",
          onPress: async () => {
            setLoading(true);
            try {
              const resp = await fetch(`/v1/meetings/${meetingId}/bot/consent`, {
                method: "DELETE",
              });
              if (resp.status === 422) {
                const err = await resp.json();
                Alert.alert("Cannot Revoke", err.detail);
                return;
              }
              if (!resp.ok) throw new Error("Failed to revoke consent");
              onConsentChange();
            } catch (err: any) {
              Alert.alert("Error", err.message);
            } finally {
              setLoading(false);
            }
          },
        },
      ]
    );
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.overlay}>
        <View style={styles.dialog}>
          {/* Header */}
          <Text style={styles.title}>Recording Bot Consent</Text>
          <Text style={styles.subtitle}>
            A Colab Notes Bot (powered by Recall.ai) will join your meeting to
            record and transcribe the session. The transcript will be stored
            securely and accessible to both participants.
          </Text>

          {/* Both-consent status */}
          <View style={styles.consentStatus}>
            <View style={styles.consentRow}>
              <View
                style={[
                  styles.consentDot,
                  myConsent ? styles.consentDotApproved : styles.consentDotPending,
                ]}
              />
              <Text style={styles.consentText}>
                You: {myConsent ? "Approved" : "Pending"}
              </Text>
            </View>
            <View style={styles.consentRow}>
              <View
                style={[
                  styles.consentDot,
                  otherConsented ? styles.consentDotApproved : styles.consentDotPending,
                ]}
              />
              <Text style={styles.consentText}>
                {otherParticipantName}: {otherConsented ? "Approved" : "Waiting"}
              </Text>
            </View>
          </View>

          {!otherConsented && myConsent && (
            <Text style={styles.waitingText}>
              Waiting for {otherParticipantName} to approve. They've been notified.
            </Text>
          )}

          {isDispatched && (
            <View style={styles.dispatchedBanner}>
              <Text style={styles.dispatchedText}>
                The bot has joined the meeting. Consent can no longer be revoked.
              </Text>
            </View>
          )}

          {/* Actions */}
          <View style={styles.actions}>
            {!myConsent && !isDispatched && (
              <Pressable
                style={[styles.allowButton, loading && styles.buttonDisabled]}
                onPress={handleAllow}
                disabled={loading}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.allowButtonText}>Allow Bot to Attend</Text>
                )}
              </Pressable>
            )}

            {myConsent && !isDispatched && (
              <Pressable
                style={[styles.revokeButton, loading && styles.buttonDisabled]}
                onPress={handleRevoke}
                disabled={loading}
              >
                <Text style={styles.revokeButtonText}>Revoke Consent</Text>
              </Pressable>
            )}

            <Pressable style={styles.closeButton} onPress={onClose}>
              <Text style={styles.closeButtonText}>
                {myConsent ? "Done" : "Maybe Later"}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  dialog: {
    backgroundColor: "#fff",
    borderRadius: 20,
    padding: 24,
    width: "100%",
    maxWidth: 400,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
  },
  title: {
    fontSize: 20,
    fontWeight: "700",
    color: "#1a1a2e",
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 14,
    color: "#6b6b8a",
    lineHeight: 20,
    marginBottom: 20,
  },
  consentStatus: {
    backgroundColor: "#f8f8ff",
    borderRadius: 12,
    padding: 16,
    gap: 12,
    marginBottom: 16,
  },
  consentRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  consentDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  consentDotApproved: {
    backgroundColor: "#22c55e",
  },
  consentDotPending: {
    backgroundColor: "#e2e8f0",
  },
  consentText: {
    fontSize: 14,
    color: "#4a4a6a",
    fontWeight: "500",
  },
  waitingText: {
    fontSize: 13,
    color: "#6b6b8a",
    fontStyle: "italic",
    marginBottom: 16,
  },
  dispatchedBanner: {
    backgroundColor: "#f0fdf4",
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  dispatchedText: {
    fontSize: 13,
    color: "#16a34a",
  },
  actions: {
    gap: 10,
  },
  allowButton: {
    backgroundColor: "#6C63FF",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
  },
  allowButtonText: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "700",
  },
  revokeButton: {
    borderWidth: 1,
    borderColor: "#ef4444",
    borderRadius: 12,
    padding: 14,
    alignItems: "center",
  },
  revokeButtonText: {
    color: "#ef4444",
    fontSize: 15,
    fontWeight: "600",
  },
  closeButton: {
    padding: 14,
    alignItems: "center",
  },
  closeButtonText: {
    color: "#6b6b8a",
    fontSize: 15,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
});
