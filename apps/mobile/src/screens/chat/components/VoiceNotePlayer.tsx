/**
 * VoiceNotePlayer — playback component for voice note messages.
 * Uses expo-av Audio.Sound.
 * Shows: play/pause button, seek bar, elapsed/total time.
 * Spec §2.6 Voice Note Playback
 */

import { Audio, AVPlaybackStatus } from "expo-av";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

interface Props {
  mediaUrl: string;
  durationMs?: number;
  isSelf: boolean;
}

function fmtTime(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toString().padStart(2, "0")}`;
}

export function VoiceNotePlayer({ mediaUrl, durationMs = 0, isSelf }: Props) {
  const soundRef = useRef<Audio.Sound | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [positionMs, setPositionMs] = useState(0);
  const [totalDurationMs, setTotalDurationMs] = useState(durationMs);

  useEffect(() => {
    return () => {
      soundRef.current?.unloadAsync();
    };
  }, []);

  const onPlaybackStatus = useCallback((status: AVPlaybackStatus) => {
    if (!status.isLoaded) return;
    setPositionMs(status.positionMillis);
    if (status.durationMillis) setTotalDurationMs(status.durationMillis);
    if (status.didJustFinish) {
      setIsPlaying(false);
      setPositionMs(0);
    }
  }, []);

  const handlePlayPause = useCallback(async () => {
    if (!soundRef.current) {
      const { sound } = await Audio.Sound.createAsync(
        { uri: mediaUrl },
        { progressUpdateIntervalMillis: 100 },
        onPlaybackStatus
      );
      soundRef.current = sound;
      await sound.playAsync();
      setIsPlaying(true);
    } else {
      const status = await soundRef.current.getStatusAsync();
      if (status.isLoaded && status.isPlaying) {
        await soundRef.current.pauseAsync();
        setIsPlaying(false);
      } else {
        await soundRef.current.playAsync();
        setIsPlaying(true);
      }
    }
  }, [mediaUrl, onPlaybackStatus]);

  const progress = totalDurationMs > 0 ? positionMs / totalDurationMs : 0;

  return (
    <View style={styles.container}>
      <TouchableOpacity onPress={handlePlayPause} style={styles.playBtn}>
        <Text style={styles.playIcon}>{isPlaying ? "⏸" : "▶"}</Text>
      </TouchableOpacity>

      {/* Progress bar */}
      <View style={styles.progressContainer}>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
        </View>
        <Text style={[styles.timeText, isSelf ? styles.timeTextSelf : styles.timeTextOther]}>
          {fmtTime(positionMs)} / {fmtTime(totalDurationMs)}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: "row", alignItems: "center", minWidth: 160, paddingVertical: 4 },
  playBtn: { width: 32, height: 32, borderRadius: 16, justifyContent: "center", alignItems: "center" },
  playIcon: { fontSize: 18 },
  progressContainer: { flex: 1, marginLeft: 8 },
  progressTrack: {
    height: 3,
    backgroundColor: "rgba(255,255,255,0.3)",
    borderRadius: 2,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: "#FFF",
    borderRadius: 2,
  },
  timeText: { fontSize: 10, marginTop: 2 },
  timeTextSelf: { color: "rgba(255,255,255,0.7)" },
  timeTextOther: { color: "#8E8E93" },
});
