/**
 * HideForThreeMonthsAction — button that hides a profile for 90 days.
 *
 * Spec FR-B-8: User can hide a profile from their feed for 3 months.
 * Calls POST /profile/{id}/hide-3mo and invokes onHidden callback with
 * the hidden_until timestamp from the API response.
 */

import React, { useState } from "react";
import { Alert, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { hideProfile } from "../../api/discovery";

interface Props {
  profileId: string;
  displayName: string;
  onHidden: (hiddenUntil: string) => void;
}

export function HideForThreeMonthsAction({
  profileId,
  displayName,
  onHidden,
}: Props): React.ReactElement {
  const [loading, setLoading] = useState(false);

  const handleHide = () => {
    Alert.alert(
      "Hide profile",
      `Hide ${displayName} from your feed for 3 months?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Hide for 3 months",
          style: "destructive",
          onPress: async () => {
            setLoading(true);
            try {
              const resp = await hideProfile(profileId);
              onHidden(resp.hidden_until);
            } catch (err: unknown) {
              const e = err as { status?: number };
              if (e?.status === 409) {
                Alert.alert("Already hidden", `${displayName} is already hidden from your feed.`);
              } else {
                Alert.alert("Error", "Could not hide profile. Please try again.");
              }
            } finally {
              setLoading(false);
            }
          },
        },
      ]
    );
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={[styles.button, loading && styles.buttonDisabled]}
        onPress={handleHide}
        disabled={loading}
      >
        <Text style={styles.buttonText}>
          {loading ? "Hiding…" : "Hide for 3 months"}
        </Text>
      </TouchableOpacity>
      <Text style={styles.subtext}>Won't appear in your feed or recommendations</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 8 },
  button: {
    backgroundColor: "#F5F5F5",
    borderColor: "#E0E0E0",
    borderWidth: 1,
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 10,
    alignItems: "center",
    marginBottom: 6,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { fontSize: 14, color: "#6A6A6A", fontWeight: "500" },
  subtext: { fontSize: 12, color: "#B0B0B0", textAlign: "center" },
});
