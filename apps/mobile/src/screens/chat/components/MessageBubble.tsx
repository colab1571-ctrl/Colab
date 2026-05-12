/**
 * MessageBubble — renders a single chat message.
 *
 * Handles: text, voice, image, video, audio, doc, system, link types.
 * Shows: pending indicator, edited label, read ticks, reply preview.
 * Integrates: ImageLightbox, VideoPlayer, VoiceNotePlayer, FileAttachment.
 */

import React, { memo } from "react";
import {
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { type ChatMessageOut } from "../../../api/chat";
import { type OptimisticMessage } from "../hooks/useMessageList";
import { VoiceNotePlayer } from "./VoiceNotePlayer";
import { MediaImage } from "./MediaImage";

interface Props {
  message: OptimisticMessage;
  isSelf: boolean;
  isRead: boolean;
  onLongPress: () => void;
  onReplyPress?: () => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export const MessageBubble = memo(function MessageBubble({
  message,
  isSelf,
  isRead,
  onLongPress,
  onReplyPress,
}: Props) {
  const isSystem = message.type === "system";
  const isPending = (message as OptimisticMessage).isPending;
  const isSoftWarn = message.moderation_status === "soft_warn";

  if (isSystem) {
    return (
      <View style={styles.systemRow}>
        <Text style={styles.systemText}>{message.body}</Text>
      </View>
    );
  }

  return (
    <TouchableOpacity
      activeOpacity={0.8}
      onLongPress={onLongPress}
      style={[styles.row, isSelf ? styles.rowSelf : styles.rowOther]}
    >
      <View style={[styles.bubble, isSelf ? styles.bubbleSelf : styles.bubbleOther]}>
        {/* Reply preview */}
        {message.reply_preview && (
          <View style={styles.replyPreview}>
            <Text style={styles.replyPreviewText} numberOfLines={1}>
              {message.reply_preview.body ?? "[media]"}
            </Text>
          </View>
        )}

        {/* Content */}
        {message.type === "text" && (
          <Text style={[styles.bodyText, isSelf ? styles.bodyTextSelf : styles.bodyTextOther]}>
            {message.body}
          </Text>
        )}

        {message.type === "voice" && message.media_url && (
          <VoiceNotePlayer
            mediaUrl={message.media_url}
            durationMs={message.duration_ms}
            isSelf={isSelf}
          />
        )}

        {message.type === "image" && message.media_url && (
          <MediaImage mediaUrl={message.media_url} />
        )}

        {(message.type === "video" || message.type === "audio" || message.type === "doc") && (
          <View style={styles.filePlaceholder}>
            <Text style={styles.fileTypeText}>{message.type.toUpperCase()}</Text>
            {message.mime && (
              <Text style={styles.fileMimeText}>{message.mime}</Text>
            )}
          </View>
        )}

        {/* Soft warn indicator */}
        {isSoftWarn && (
          <Text style={styles.softWarnLabel}>⚠ Possible guideline violation</Text>
        )}

        {/* Metadata row */}
        <View style={styles.metaRow}>
          {message.edited_at && (
            <Text style={styles.editedLabel}>edited </Text>
          )}
          <Text style={[styles.timeText, isSelf ? styles.timeTextSelf : styles.timeTextOther]}>
            {formatTime(message.created_at)}
          </Text>
          {isSelf && (
            <Text style={styles.tickText}>
              {isPending ? "⏱" : isRead ? "✓✓" : "✓"}
            </Text>
          )}
        </View>
      </View>
    </TouchableOpacity>
  );
});

const styles = StyleSheet.create({
  row: { marginVertical: 2, paddingHorizontal: 4 },
  rowSelf: { alignItems: "flex-end" },
  rowOther: { alignItems: "flex-start" },
  bubble: {
    maxWidth: "78%",
    borderRadius: 18,
    paddingHorizontal: 12,
    paddingVertical: 8,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
  },
  bubbleSelf: { backgroundColor: "#007AFF" },
  bubbleOther: { backgroundColor: "#ECECEC" },
  bodyText: { fontSize: 15, lineHeight: 21 },
  bodyTextSelf: { color: "#FFF" },
  bodyTextOther: { color: "#1C1C1E" },
  metaRow: { flexDirection: "row", alignItems: "center", marginTop: 2 },
  timeText: { fontSize: 11 },
  timeTextSelf: { color: "rgba(255,255,255,0.7)" },
  timeTextOther: { color: "#8E8E93" },
  tickText: { fontSize: 11, color: "rgba(255,255,255,0.7)", marginLeft: 4 },
  editedLabel: { fontSize: 10, color: "rgba(255,255,255,0.6)", fontStyle: "italic" },
  systemRow: { alignItems: "center", marginVertical: 8 },
  systemText: { fontSize: 12, color: "#8E8E93", fontStyle: "italic" },
  softWarnLabel: { fontSize: 10, color: "#FF9500", marginTop: 2 },
  replyPreview: {
    borderLeftWidth: 2,
    borderLeftColor: "rgba(255,255,255,0.5)",
    paddingLeft: 6,
    marginBottom: 4,
  },
  replyPreviewText: { fontSize: 12, color: "rgba(255,255,255,0.7)", fontStyle: "italic" },
  filePlaceholder: {
    padding: 8,
    backgroundColor: "rgba(0,0,0,0.1)",
    borderRadius: 8,
    alignItems: "center",
    minWidth: 120,
  },
  fileTypeText: { fontSize: 13, fontWeight: "700", color: "#FFF" },
  fileMimeText: { fontSize: 10, color: "rgba(255,255,255,0.6)", marginTop: 2 },
});
