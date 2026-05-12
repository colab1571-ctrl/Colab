/**
 * ReadOnlyBanner — shown at top of chat when room is read_only or archived.
 * Spec §6 Block-aware behavior, T-42.
 */

import React from "react";
import { StyleSheet, Text, View } from "react-native";

interface Props {
  state: "read_only" | "archived";
}

const MESSAGES: Record<string, string> = {
  read_only: "This conversation is now read-only. You can still view the chat history.",
  archived: "This conversation is archived.",
};

export function ReadOnlyBanner({ state }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>{MESSAGES[state] ?? "This chat is read-only."}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#FFF3CD",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#FFEAA7",
  },
  text: { fontSize: 13, color: "#856404", textAlign: "center", lineHeight: 18 },
});
