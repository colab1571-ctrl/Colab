/**
 * MockupConsentModal — AI Collab Preview consent UI.
 *
 * Party A (initiator): shows brief input + lifespan selector + watermark policy.
 * Party B (responder): shows brief from A + watermark policy + Accept/Decline CTAs.
 *
 * Spec: §4.3 Consent Modal Content, §10.2 POST /collabs/{id}/mockup/consent
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

interface ConsentRecord {
  consent_id: string;
  status: "pending_b" | "approved" | "rejected" | "expired" | "generated";
  brief: string;
  lifespan_days: 1 | 14;
  requested_by: string; // user_id of party A
}

interface Props {
  visible: boolean;
  onClose: () => void;
  collabId: string;
  currentUserId: string;
  /** If provided, user is party B responding to this consent */
  pendingConsent?: ConsentRecord;
  onConsentCreated?: (consentId: string) => void;
  onConsentApproved?: (consentId: string, aiInteractionId: string) => void;
}

const WATERMARK_POLICY =
  "This mockup will be permanently watermarked with both your names and a timestamp. " +
  "It is for preview purposes only.";

const VIEWER_RESTRICTION =
  "Only you and your collaborator can view this mockup.";

const IP_REMINDER =
  "Generating this mockup does not transfer any IP rights.";

export function MockupConsentModal({
  visible,
  onClose,
  collabId,
  currentUserId,
  pendingConsent,
  onConsentCreated,
  onConsentApproved,
}: Props) {
  const isPartyB = !!pendingConsent && pendingConsent.requested_by !== currentUserId;

  const [brief, setBrief] = useState("");
  const [lifespanDays, setLifespanDays] = useState<1 | 14>(1);
  const [loading, setLoading] = useState(false);

  const handlePartyASubmit = async () => {
    if (!brief.trim()) {
      Alert.alert("Brief required", "Please describe what you want to generate.");
      return;
    }
    setLoading(true);
    try {
      const resp = await fetch(`/collabs/${collabId}/mockup/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lifespan_days: lifespanDays, brief: brief.trim(), kind: "image" }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Failed to create consent");
      }
      const data = await resp.json();
      onConsentCreated?.(data.consent_id);
      onClose();
      Alert.alert(
        "Consent sent",
        "Waiting for your collaborator to agree. You'll be notified when they respond.",
      );
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to create consent request");
    } finally {
      setLoading(false);
    }
  };

  const handlePartyBRespond = async (accept: boolean) => {
    if (!pendingConsent) return;
    if (!accept) {
      setLoading(true);
      try {
        await fetch(`/collabs/${collabId}/mockup/consent`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ consent_id: pendingConsent.consent_id, accept: false }),
        });
      } catch {
        // best-effort
      } finally {
        setLoading(false);
        onClose();
      }
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch(`/collabs/${collabId}/mockup/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ consent_id: pendingConsent.consent_id, accept: true }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Failed to accept consent");
      }
      const data = await resp.json();
      onConsentApproved?.(data.consent_id, data.ai_interaction_id);
      onClose();
      Alert.alert(
        "Generating!",
        "Your AI mockup is being created. Both of you will be notified when it's ready.",
      );
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to accept consent");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>
          {isPartyB ? "AI Collab Preview Request" : "Generate AI Collab Preview"}
        </Text>

        {/* Party B: show party A's brief */}
        {isPartyB && pendingConsent && (
          <View style={styles.section}>
            <Text style={styles.label}>Your collaborator's brief:</Text>
            <Text style={styles.briefText}>{pendingConsent.brief}</Text>
            <Text style={styles.label}>
              Preview lifespan: {pendingConsent.lifespan_days === 1 ? "1 day" : "14 days"}
            </Text>
          </View>
        )}

        {/* Party A: brief input */}
        {!isPartyB && (
          <View style={styles.section}>
            <Text style={styles.label}>Describe what you want to generate (max 500 chars):</Text>
            <TextInput
              style={styles.briefInput}
              value={brief}
              onChangeText={(t) => setBrief(t.slice(0, 500))}
              placeholder="e.g. A visual concept for our indie film poster, dark and dramatic"
              multiline
              maxLength={500}
            />
            <Text style={styles.charCount}>{brief.length}/500</Text>

            <Text style={styles.label}>Preview lifespan:</Text>
            <View style={styles.lifespanRow}>
              {([1, 14] as const).map((days) => (
                <TouchableOpacity
                  key={days}
                  style={[
                    styles.lifespanOption,
                    lifespanDays === days && styles.lifespanOptionSelected,
                  ]}
                  onPress={() => setLifespanDays(days)}
                >
                  <Text
                    style={[
                      styles.lifespanText,
                      lifespanDays === days && styles.lifespanTextSelected,
                    ]}
                  >
                    {days === 1 ? "1 Day" : "14 Days"}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* Watermark policy — shown to both parties */}
        <View style={styles.policySection}>
          <Text style={styles.policyTitle}>AI Mockup Policy</Text>
          <Text style={styles.policyText}>{WATERMARK_POLICY}</Text>
          <Text style={styles.policyText}>{VIEWER_RESTRICTION}</Text>
          <Text style={styles.policyText}>{IP_REMINDER}</Text>
        </View>

        {/* CTAs */}
        {isPartyB ? (
          <View style={styles.ctaRow}>
            <TouchableOpacity
              style={[styles.cta, styles.ctaDecline]}
              onPress={() => handlePartyBRespond(false)}
              disabled={loading}
            >
              <Text style={styles.ctaDeclineText}>Decline</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.cta, styles.ctaAccept]}
              onPress={() => handlePartyBRespond(true)}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.ctaAcceptText}>Accept &amp; Generate</Text>
              )}
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.ctaRow}>
            <TouchableOpacity style={[styles.cta, styles.ctaDecline]} onPress={onClose}>
              <Text style={styles.ctaDeclineText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.cta, styles.ctaAccept]}
              onPress={handlePartyASubmit}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.ctaAcceptText}>Send Request</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 20,
    paddingBottom: 40,
  },
  title: {
    fontSize: 20,
    fontWeight: "700",
    marginBottom: 20,
    textAlign: "center",
    color: "#1a1a2e",
  },
  section: {
    marginBottom: 20,
  },
  label: {
    fontSize: 14,
    fontWeight: "600",
    color: "#444",
    marginBottom: 6,
    marginTop: 12,
  },
  briefInput: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    minHeight: 80,
    textAlignVertical: "top",
    color: "#222",
  },
  briefText: {
    fontSize: 14,
    color: "#333",
    backgroundColor: "#f5f5f5",
    padding: 12,
    borderRadius: 8,
    fontStyle: "italic",
  },
  charCount: {
    fontSize: 12,
    color: "#aaa",
    textAlign: "right",
    marginTop: 4,
  },
  lifespanRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 4,
  },
  lifespanOption: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: "center",
  },
  lifespanOptionSelected: {
    borderColor: "#6c5ce7",
    backgroundColor: "#f0eeff",
  },
  lifespanText: {
    fontSize: 14,
    color: "#666",
  },
  lifespanTextSelected: {
    color: "#6c5ce7",
    fontWeight: "600",
  },
  policySection: {
    backgroundColor: "#fafafa",
    borderRadius: 10,
    padding: 14,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: "#e8e8e8",
  },
  policyTitle: {
    fontSize: 13,
    fontWeight: "700",
    color: "#555",
    marginBottom: 8,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  policyText: {
    fontSize: 13,
    color: "#666",
    lineHeight: 18,
    marginBottom: 6,
  },
  ctaRow: {
    flexDirection: "row",
    gap: 12,
  },
  cta: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  ctaDecline: {
    borderWidth: 1,
    borderColor: "#ddd",
    backgroundColor: "#fff",
  },
  ctaAccept: {
    backgroundColor: "#6c5ce7",
  },
  ctaDeclineText: {
    fontSize: 15,
    color: "#666",
    fontWeight: "600",
  },
  ctaAcceptText: {
    fontSize: 15,
    color: "#fff",
    fontWeight: "700",
  },
});
