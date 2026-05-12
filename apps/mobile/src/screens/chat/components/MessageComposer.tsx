/**
 * MessageComposer — text input + voice recorder + file/image picker.
 *
 * Hold-to-record voice notes (expo-av), image picker, file picker.
 * Typing indicator debounce: starts on keystroke, stops 3s after last keystroke.
 */

import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

import { confirmUpload, getUploadUrl } from "../../../api/chat";
import { VoiceRecorder } from "./VoiceRecorder";

const ALLOWED_DOC_MIMES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
];

interface Props {
  roomId: string;
  onSendText: (body: string) => Promise<void>;
  onTypingStart: () => void;
  onTypingStop: () => void;
  disabled?: boolean;
}

export function MessageComposer({
  roomId,
  onSendText,
  onTypingStart,
  onTypingStop,
  disabled = false,
}: Props) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showVoice, setShowVoice] = useState(false);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTypingRef = useRef(false);

  const handleTextChange = useCallback((value: string) => {
    setText(value);
    if (!isTypingRef.current) {
      isTypingRef.current = true;
      onTypingStart();
    }
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => {
      isTypingRef.current = false;
      onTypingStop();
    }, 3000);
  }, [onTypingStart, onTypingStop]);

  const handleSend = useCallback(async () => {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setText("");
    isTypingRef.current = false;
    onTypingStop();
    try {
      await onSendText(body);
    } finally {
      setSending(false);
    }
  }, [text, sending, onSendText, onTypingStop]);

  const handleImagePick = useCallback(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
      allowsEditing: false,
    });
    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const mime = asset.mimeType ?? "image/jpeg";
    const size = asset.fileSize ?? 0;

    if (size > 10 * 1024 * 1024) {
      Alert.alert("File too large", "Images must be under 10MB.");
      return;
    }

    await uploadMedia(asset.uri, "image", mime, size);
  }, [roomId]);

  const handleFilePick = useCallback(async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ALLOWED_DOC_MIMES,
      copyToCacheDirectory: true,
    });
    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const mime = asset.mimeType ?? "application/pdf";
    const size = asset.size ?? 0;

    if (size > 25 * 1024 * 1024) {
      Alert.alert("File too large", "Documents must be under 25MB.");
      return;
    }

    await uploadMedia(asset.uri, "doc", mime, size);
  }, [roomId]);

  const uploadMedia = useCallback(
    async (
      uri: string,
      kind: "image" | "audio" | "video" | "doc" | "voice",
      mime: string,
      sizeBytes: number,
      durationMs?: number
    ) => {
      setUploading(true);
      try {
        // 1. Get presigned URL
        const { upload_url, s3_key } = await getUploadUrl({
          room_id: roomId,
          kind,
          mime,
          size_bytes: sizeBytes,
        });

        // 2. Upload directly to S3
        const fileData = await fetch(uri);
        const blob = await fileData.blob();
        await fetch(upload_url, {
          method: "PUT",
          body: blob,
          headers: { "Content-Type": mime },
        });

        // 3. Confirm to media-svc (triggers scan + WS delivery)
        await confirmUpload({
          room_id: roomId,
          kind,
          s3_key,
          mime,
          size_bytes: sizeBytes,
          duration_ms: durationMs,
        });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        Alert.alert("Upload failed", msg);
      } finally {
        setUploading(false);
      }
    },
    [roomId]
  );

  const handleVoiceSend = useCallback(
    async (uri: string, durationMs: number) => {
      setShowVoice(false);
      const size = 0; // Expo doesn't always provide size; server validates
      await uploadMedia(uri, "voice", "audio/mp4", size, durationMs);
    },
    [uploadMedia]
  );

  if (showVoice) {
    return (
      <VoiceRecorder
        onSend={handleVoiceSend}
        onCancel={() => setShowVoice(false)}
      />
    );
  }

  return (
    <View style={styles.container}>
      {/* Text input */}
      <TextInput
        style={styles.input}
        placeholder="Message…"
        placeholderTextColor="#999"
        value={text}
        onChangeText={handleTextChange}
        multiline
        maxLength={4000}
        editable={!disabled}
        returnKeyType="default"
      />

      {/* Action buttons */}
      <View style={styles.actions}>
        {uploading ? (
          <ActivityIndicator size="small" style={{ marginRight: 8 }} />
        ) : (
          <>
            <TouchableOpacity onPress={handleImagePick} style={styles.iconBtn} disabled={disabled}>
              <Text style={styles.iconText}>🖼</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleFilePick} style={styles.iconBtn} disabled={disabled}>
              <Text style={styles.iconText}>📎</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowVoice(true)} style={styles.iconBtn} disabled={disabled}>
              <Text style={styles.iconText}>🎤</Text>
            </TouchableOpacity>
          </>
        )}

        {text.trim().length > 0 && (
          <TouchableOpacity
            onPress={handleSend}
            style={[styles.sendBtn, (sending || disabled) && styles.sendBtnDisabled]}
            disabled={sending || disabled}
          >
            {sending ? (
              <ActivityIndicator size="small" color="#FFF" />
            ) : (
              <Text style={styles.sendText}>Send</Text>
            )}
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: 8,
    paddingVertical: 8,
    backgroundColor: "#FFF",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#DDD",
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#E0E0E0",
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    backgroundColor: "#F7F7F7",
    marginRight: 8,
  },
  actions: { flexDirection: "row", alignItems: "center" },
  iconBtn: { padding: 6, marginHorizontal: 2 },
  iconText: { fontSize: 20 },
  sendBtn: {
    backgroundColor: "#007AFF",
    borderRadius: 20,
    paddingHorizontal: 18,
    paddingVertical: 10,
    marginLeft: 4,
  },
  sendBtnDisabled: { backgroundColor: "#B0C8F0" },
  sendText: { color: "#FFF", fontWeight: "700", fontSize: 14 },
});
