/**
 * MatchCelebrationHandoff — "Match!" screen that opens chat room.
 *
 * Consumes match.created event (via push notification or navigation param).
 * Shows celebration animation, then navigates to ChatRoomScreen.
 *
 * Spec AC-01: Match → room auto-created within 2s.
 */

import React, { useCallback, useEffect, useRef } from "react";
import {
  Animated,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

interface MatchData {
  room_id: string;
  collaboration_id: string;
  other_profile: {
    profile_id: string;
    display_name: string | null;
    avatar_url: string | null;
  };
}

interface Props {
  matchData: MatchData;
  onOpenChat: (roomId: string, collaborationId: string, otherProfile: MatchData["other_profile"]) => void;
  onDismiss: () => void;
}

export function MatchCelebrationHandoff({ matchData, onOpenChat, onDismiss }: Props) {
  const scaleAnim = useRef(new Animated.Value(0)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const confettiAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Celebration animation sequence
    Animated.sequence([
      Animated.spring(scaleAnim, {
        toValue: 1,
        tension: 60,
        friction: 6,
        useNativeDriver: true,
      }),
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }),
    ]).start();

    Animated.loop(
      Animated.timing(confettiAnim, {
        toValue: 1,
        duration: 2000,
        useNativeDriver: true,
      }),
      { iterations: 3 }
    ).start();
  }, []);

  const handleOpenChat = useCallback(() => {
    onOpenChat(matchData.room_id, matchData.collaboration_id, matchData.other_profile);
  }, [matchData, onOpenChat]);

  return (
    <View style={styles.container}>
      {/* Confetti placeholder — production uses lottie-react-native */}
      <View style={styles.confetti}>
        {["🎉", "✨", "🎊", "⭐", "🎈"].map((emoji, i) => (
          <Animated.Text
            key={i}
            style={[
              styles.confettiEmoji,
              {
                top: 40 + i * 30,
                left: 20 + (i % 3) * 100,
                opacity: fadeAnim,
              },
            ]}
          >
            {emoji}
          </Animated.Text>
        ))}
      </View>

      <Animated.View style={[styles.card, { transform: [{ scale: scaleAnim }] }]}>
        <Text style={styles.matchLabel}>Match!</Text>

        <Text style={styles.subtitle}>
          You matched with{" "}
          <Text style={styles.name}>{matchData.other_profile.display_name ?? "someone"}</Text>!
        </Text>

        <Text style={styles.body}>
          Your collaboration workspace is ready. Start chatting to kick off your project.
        </Text>

        <Animated.View style={{ opacity: fadeAnim }}>
          <TouchableOpacity style={styles.chatBtn} onPress={handleOpenChat}>
            <Text style={styles.chatBtnText}>Open Chat →</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.dismissBtn} onPress={onDismiss}>
            <Text style={styles.dismissText}>Later</Text>
          </TouchableOpacity>
        </Animated.View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.85)",
    justifyContent: "center",
    alignItems: "center",
  },
  confetti: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  confettiEmoji: { position: "absolute", fontSize: 28 },
  card: {
    backgroundColor: "#FFF",
    borderRadius: 28,
    padding: 32,
    alignItems: "center",
    width: "85%",
    maxWidth: 360,
    shadowColor: "#000",
    shadowOpacity: 0.25,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 16,
  },
  matchLabel: {
    fontSize: 52,
    fontWeight: "900",
    color: "#007AFF",
    letterSpacing: -1,
    marginBottom: 8,
  },
  subtitle: { fontSize: 18, color: "#1C1C1E", textAlign: "center", marginBottom: 12 },
  name: { fontWeight: "700", color: "#007AFF" },
  body: { fontSize: 14, color: "#666", textAlign: "center", lineHeight: 20, marginBottom: 24 },
  chatBtn: {
    backgroundColor: "#007AFF",
    borderRadius: 16,
    paddingHorizontal: 40,
    paddingVertical: 16,
    marginBottom: 12,
    minWidth: 200,
    alignItems: "center",
  },
  chatBtnText: { color: "#FFF", fontWeight: "800", fontSize: 16 },
  dismissBtn: { alignItems: "center", padding: 8 },
  dismissText: { color: "#8E8E93", fontSize: 14 },
});
