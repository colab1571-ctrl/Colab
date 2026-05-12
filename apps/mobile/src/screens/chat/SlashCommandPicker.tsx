/**
 * SlashCommandPicker — in-composer slash command UI.
 *
 * Displayed when the user types "/" in the chat composer.
 * Lists the 5 AI commands. Gated to Premium/Pro with upsell modal for Free users.
 *
 * Spec: §3 Five-Command Catalogue, §12 AC-01 Free user upsell gate
 */

import React, { useCallback } from "react";
import {
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

export type SlashCommand =
  | "mockup-image"
  | "mockup-audio"
  | "summarize-chat"
  | "brainstorm"
  | "palette";

interface CommandDef {
  command: SlashCommand;
  label: string;
  description: string;
  argPlaceholder: string;
  isAsync: boolean; // true = 202 async (image/audio)
}

const COMMANDS: CommandDef[] = [
  {
    command: "mockup-image",
    label: "/mockup-image",
    description: "Generate a watermarked visual concept image",
    argPlaceholder: "<describe the visual>",
    isAsync: true,
  },
  {
    command: "mockup-audio",
    label: "/mockup-audio",
    description: "Generate a short watermarked audio clip",
    argPlaceholder: "<describe the sound>",
    isAsync: true,
  },
  {
    command: "summarize-chat",
    label: "/summarize-chat",
    description: "Summarize the last N messages (default 50)",
    argPlaceholder: "[N]",
    isAsync: false,
  },
  {
    command: "brainstorm",
    label: "/brainstorm",
    description: "Generate creative ideas on a topic",
    argPlaceholder: "<topic>",
    isAsync: false,
  },
  {
    command: "palette",
    label: "/palette",
    description: "Generate a color palette with hex codes",
    argPlaceholder: "<mood or concept>",
    isAsync: false,
  },
];

interface Props {
  /** User's current subscription tier */
  userTier: "free" | "premium" | "pro";
  /** Called with the selected command string (e.g. "/mockup-image ") */
  onSelectCommand: (commandText: string) => void;
  /** Filter by prefix typed so far (e.g. "mock") */
  filter?: string;
}

function UpsellBadge() {
  return (
    <View style={styles.upsellBadge}>
      <Text style={styles.upsellBadgeText}>Premium</Text>
    </View>
  );
}

function AsyncBadge() {
  return (
    <View style={styles.asyncBadge}>
      <Text style={styles.asyncBadgeText}>~45s</Text>
    </View>
  );
}

export function SlashCommandPicker({ userTier, onSelectCommand, filter }: Props) {
  const isPremium = userTier === "premium" || userTier === "pro";

  const filteredCommands = filter
    ? COMMANDS.filter(
        (c) =>
          c.command.startsWith(filter.toLowerCase()) ||
          c.label.includes(filter.toLowerCase()),
      )
    : COMMANDS;

  const handleSelect = useCallback(
    (cmd: CommandDef) => {
      if (!isPremium) {
        Alert.alert(
          "Premium Feature",
          "AI commands are available to Premium and Pro subscribers. Upgrade to unlock brainstorms, mockups, and more.",
          [
            { text: "Maybe Later", style: "cancel" },
            {
              text: "Upgrade",
              onPress: () => {
                // Navigate to upgrade screen
                // navigation.navigate("Upgrade");
              },
            },
          ],
        );
        return;
      }
      // Insert command + placeholder into composer
      const text = `${cmd.label} ${cmd.argPlaceholder !== "[N]" ? "" : ""}`;
      onSelectCommand(text.trimEnd());
    },
    [isPremium, onSelectCommand],
  );

  if (filteredCommands.length === 0) return null;

  return (
    <View style={styles.container}>
      <Text style={styles.header}>AI Commands</Text>
      <FlatList
        data={filteredCommands}
        keyExtractor={(item) => item.command}
        keyboardShouldPersistTaps="handled"
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.commandRow}
            onPress={() => handleSelect(item)}
            activeOpacity={0.7}
          >
            <View style={styles.commandLeft}>
              <Text style={[styles.commandLabel, !isPremium && styles.commandLabelLocked]}>
                {item.label}{" "}
                <Text style={styles.commandArg}>{item.argPlaceholder}</Text>
              </Text>
              <Text style={styles.commandDesc}>{item.description}</Text>
            </View>
            <View style={styles.commandRight}>
              {!isPremium && <UpsellBadge />}
              {isPremium && item.isAsync && <AsyncBadge />}
            </View>
          </TouchableOpacity>
        )}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        scrollEnabled={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#fff",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#e0e0e0",
    borderRadius: 12,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 6,
  },
  header: {
    fontSize: 11,
    fontWeight: "700",
    color: "#aaa",
    textTransform: "uppercase",
    letterSpacing: 0.8,
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 4,
  },
  commandRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 10,
    gap: 12,
  },
  commandLeft: {
    flex: 1,
    gap: 2,
  },
  commandLabel: {
    fontSize: 14,
    fontWeight: "600",
    color: "#6c5ce7",
    fontFamily: "monospace",
  },
  commandLabelLocked: {
    color: "#bbb",
  },
  commandArg: {
    color: "#aaa",
    fontWeight: "400",
  },
  commandDesc: {
    fontSize: 12,
    color: "#888",
  },
  commandRight: {
    alignItems: "flex-end",
    gap: 4,
  },
  upsellBadge: {
    backgroundColor: "#f0eeff",
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  upsellBadgeText: {
    fontSize: 10,
    fontWeight: "700",
    color: "#6c5ce7",
    textTransform: "uppercase",
  },
  asyncBadge: {
    backgroundColor: "#e8f5e9",
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  asyncBadgeText: {
    fontSize: 10,
    color: "#2e7d32",
    fontWeight: "600",
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#f0f0f0",
    marginLeft: 14,
  },
});
