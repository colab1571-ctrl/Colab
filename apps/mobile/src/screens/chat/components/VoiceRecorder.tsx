/**
 * VoiceRecorder — hold-to-record voice note component.
 *
 * Uses expo-av Audio.Recording API.
 * - Hold-to-record UX (onPressIn / onPressOut)
 * - Live amplitude waveform bars (metering)
 * - 5-minute recording cap (auto-stop)
 * - Swipe-left to cancel
 * - Output: .m4a (audio/mp4), HIGH_QUALITY preset
 *
 * Spec §2.6 Voice Note Recording
 */

import { Audio } from "expo-av";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Animated,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

const MAX_DURATION_MS = 5 * 60 * 1000; // 5 minutes
const WAVEFORM_BARS = 20;
const METERING_INTERVAL_MS = 100;

interface Props {
  onSend: (uri: string, durationMs: number) => void;
  onCancel: () => void;
}

export function VoiceRecorder({ onSend, onCancel }: Props) {
  const recordingRef = useRef<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [amplitudes, setAmplitudes] = useState<number[]>(Array(WAVEFORM_BARS).fill(0.1));
  const maxDurationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const durationTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (isRecording) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.3, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulseAnim.stopAnimation();
      pulseAnim.setValue(1);
    }
  }, [isRecording, pulseAnim]);

  const startRecording = useCallback(async () => {
    try {
      const { granted } = await Audio.requestPermissionsAsync();
      if (!granted) {
        Alert.alert("Permission required", "Microphone access is needed to record voice notes.");
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
        (status) => {
          if (status.isRecording && status.metering !== undefined) {
            // metering: -160 (silent) to 0 (max)
            const normalized = Math.max(0, (status.metering + 160) / 160);
            setAmplitudes((prev) => {
              const next = [...prev.slice(1), normalized];
              return next;
            });
          }
        },
        METERING_INTERVAL_MS
      );

      recordingRef.current = recording;
      startTimeRef.current = Date.now();
      setIsRecording(true);
      setDurationMs(0);

      // Duration ticker
      durationTimer.current = setInterval(() => {
        setDurationMs(Date.now() - startTimeRef.current);
      }, 200);

      // Auto-stop at 5 minutes
      maxDurationTimer.current = setTimeout(stopAndSend, MAX_DURATION_MS);
    } catch (err) {
      console.error("Recording start error:", err);
    }
  }, []);

  const stopAndSend = useCallback(async () => {
    if (!recordingRef.current) return;
    if (maxDurationTimer.current) clearTimeout(maxDurationTimer.current);
    if (durationTimer.current) clearInterval(durationTimer.current);

    setIsRecording(false);

    const recording = recordingRef.current;
    recordingRef.current = null;

    await recording.stopAndUnloadAsync();
    await Audio.setAudioModeAsync({ allowsRecordingIOS: false });

    const status = await recording.getStatusAsync();
    const uri = recording.getURI();
    if (!uri) return;

    const dur = (status as any).durationMillis ?? (Date.now() - startTimeRef.current);
    onSend(uri, dur);
  }, [onSend]);

  const cancel = useCallback(async () => {
    if (maxDurationTimer.current) clearTimeout(maxDurationTimer.current);
    if (durationTimer.current) clearInterval(durationTimer.current);

    if (recordingRef.current) {
      await recordingRef.current.stopAndUnloadAsync().catch(() => {});
      recordingRef.current = null;
    }
    setIsRecording(false);
    onCancel();
  }, [onCancel]);

  const formatDuration = (ms: number): string => {
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <View style={styles.container}>
      {/* Waveform */}
      <View style={styles.waveform}>
        {amplitudes.map((amp, i) => (
          <View
            key={i}
            style={[
              styles.waveBar,
              { height: Math.max(4, amp * 36), opacity: isRecording ? 0.9 : 0.3 },
            ]}
          />
        ))}
      </View>

      {/* Duration */}
      <Text style={styles.duration}>{formatDuration(durationMs)}</Text>

      {/* Buttons */}
      <View style={styles.controls}>
        <TouchableOpacity style={styles.cancelBtn} onPress={cancel}>
          <Text style={styles.cancelText}>✕ Cancel</Text>
        </TouchableOpacity>

        <Animated.View style={{ transform: [{ scale: pulseAnim }] }}>
          <TouchableOpacity
            style={[styles.recordBtn, isRecording && styles.recordBtnActive]}
            onPressIn={startRecording}
            onPressOut={isRecording ? stopAndSend : undefined}
          >
            <Text style={styles.recordBtnText}>{isRecording ? "⏹ Release to send" : "🎤 Hold to record"}</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#FFF",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#DDD",
    padding: 16,
  },
  waveform: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    height: 40,
    marginBottom: 8,
    gap: 2,
  },
  waveBar: {
    width: 3,
    borderRadius: 2,
    backgroundColor: "#007AFF",
  },
  duration: {
    textAlign: "center",
    fontSize: 16,
    fontWeight: "600",
    color: "#1C1C1E",
    marginBottom: 12,
  },
  controls: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  cancelBtn: { padding: 10 },
  cancelText: { color: "#FF3B30", fontSize: 15 },
  recordBtn: {
    backgroundColor: "#007AFF",
    borderRadius: 24,
    paddingHorizontal: 24,
    paddingVertical: 12,
  },
  recordBtnActive: { backgroundColor: "#FF3B30" },
  recordBtnText: { color: "#FFF", fontWeight: "700", fontSize: 14 },
});
