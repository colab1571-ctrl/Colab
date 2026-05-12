/**
 * ChatRoomScreen — main real-time 1:1 chat view.
 *
 * Features:
 * - FlashList (virtualized, inverted) for message list
 * - Real-time WS updates via useChatSocket hook
 * - Optimistic send + pending indicator
 * - Infinite scroll upward (older messages)
 * - Typing indicator (animated 3-dot bubble)
 * - Presence indicator (online dot on header avatar)
 * - Read receipts (single/double tick on sender bubbles)
 * - Reply-to threading (inline preview bar)
 * - Read-only room banner
 * - Auto-scroll to bottom on new message
 *
 * Spec: §3 WS protocol, §4 reconnect+resume, §7 read receipts, §6 block-aware
 */

import { FlashList } from "@shopify/flash-list";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { type ChatMessageOut } from "../../api/chat";
import { useAuthStore } from "../../state/auth.store";
import { MessageBubble } from "./components/MessageBubble";
import { MessageComposer } from "./components/MessageComposer";
import { TypingIndicator } from "./components/TypingIndicator";
import { ReadOnlyBanner } from "./components/ReadOnlyBanner";
import { useChatSocket } from "./hooks/useChatSocket";
import { useMessageList } from "./hooks/useMessageList";

interface Props {
  roomId: string;
  collaborationId: string;
  otherParticipant: {
    profile_id: string;
    display_name: string | null;
    avatar_url: string | null;
  };
}

export function ChatRoomScreen({ roomId, collaborationId, otherParticipant }: Props) {
  const profileId = useAuthStore((s) => s.profileId) ?? "";
  const flashListRef = useRef<FlashList<ChatMessageOut>>(null);

  const {
    messages,
    hasMore,
    loadingOlder,
    initialLoaded,
    loadInitial,
    loadOlder,
    appendMessage,
    mergeReplay,
    confirmOptimistic,
  } = useMessageList(roomId);

  const [roomState, setRoomState] = useState<"open" | "read_only" | "archived">("open");
  const [isOtherTyping, setIsOtherTyping] = useState(false);
  const [isOtherOnline, setIsOtherOnline] = useState(false);
  const [otherLastSeen, setOtherLastSeen] = useState<string | null>(null);
  const [otherReadMsgId, setOtherReadMsgId] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<ChatMessageOut | null>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [newMsgCount, setNewMsgCount] = useState(0);

  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---------------------------------------------------------------------------
  // WS callbacks
  // ---------------------------------------------------------------------------

  const handleMessage = useCallback(
    (msg: ChatMessageOut) => {
      appendMessage(msg);
      if (isNearBottom) {
        setTimeout(() => flashListRef.current?.scrollToEnd({ animated: true }), 50);
      } else {
        setNewMsgCount((c) => c + 1);
      }
    },
    [appendMessage, isNearBottom]
  );

  const handleReplay = useCallback(
    (msgs: ChatMessageOut[], _hasMore: boolean) => {
      mergeReplay(msgs);
    },
    [mergeReplay]
  );

  const handleTyping = useCallback(
    (pid: string, state: "start" | "stop") => {
      if (pid === otherParticipant.profile_id) {
        setIsOtherTyping(state === "start");
        if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
        if (state === "start") {
          typingTimeoutRef.current = setTimeout(() => setIsOtherTyping(false), 5000);
        }
      }
    },
    [otherParticipant.profile_id]
  );

  const handlePresence = useCallback(
    (pid: string, online: boolean, lastSeenAt: string) => {
      if (pid === otherParticipant.profile_id) {
        setIsOtherOnline(online);
        setOtherLastSeen(lastSeenAt);
      }
    },
    [otherParticipant.profile_id]
  );

  const handleRead = useCallback(
    (pid: string, upToMsgId: string, _readAt: string) => {
      if (pid === otherParticipant.profile_id) {
        setOtherReadMsgId(upToMsgId);
      }
    },
    [otherParticipant.profile_id]
  );

  const handleError = useCallback((code: string, message: string) => {
    if (code === "MODERATION_REJECTED") {
      Alert.alert("Message not sent", "Your message was flagged by our safety system.");
    } else if (code === "MODERATION_HOLD") {
      Alert.alert("Message under review", "Your message is being reviewed before delivery.");
    } else if (code === "ROOM_READ_ONLY") {
      // Banner shown via roomState
    }
  }, []);

  const { connectionState, isConnected, sendMessage, sendTyping, sendReadAck } = useChatSocket({
    roomId,
    profileId,
    onMessage: handleMessage,
    onReplay: handleReplay,
    onTyping: handleTyping,
    onPresence: handlePresence,
    onRead: handleRead,
    onRoomState: setRoomState,
    onError: handleError,
  });

  // ---------------------------------------------------------------------------
  // Initial load
  // ---------------------------------------------------------------------------

  useEffect(() => {
    loadInitial();
  }, [roomId]);

  // ---------------------------------------------------------------------------
  // Auto read ack when near bottom and new messages arrive
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (isNearBottom && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.sender_profile_id !== profileId) {
        sendReadAck(lastMsg.id);
      }
    }
  }, [messages, isNearBottom, profileId, sendReadAck]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleSend = useCallback(
    async (body: string) => {
      if (roomState !== "open") return;
      await sendMessage(body, replyTo?.id);
      setReplyTo(null);
    },
    [sendMessage, replyTo, roomState]
  );

  const handleScrollToBottom = useCallback(() => {
    flashListRef.current?.scrollToEnd({ animated: true });
    setNewMsgCount(0);
    setIsNearBottom(true);
  }, []);

  const handleScroll = useCallback((event: any) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const distanceFromBottom =
      contentSize.height - (contentOffset.y + layoutMeasurement.height);
    const nearBottom = distanceFromBottom < 100;
    setIsNearBottom(nearBottom);
    if (nearBottom) setNewMsgCount(0);
  }, []);

  const handleLongPress = useCallback((msg: ChatMessageOut) => {
    const options = ["Reply", "Copy"];
    if (msg.sender_profile_id === profileId && msg.type === "text") {
      options.push("Edit");
    }
    options.push("Report", "Cancel");
    Alert.alert("Message", undefined, [
      { text: "Reply", onPress: () => setReplyTo(msg) },
      { text: "Copy" },
      ...(msg.sender_profile_id === profileId && msg.type === "text"
        ? [{ text: "Edit" }]
        : []),
      { text: "Report" },
      { text: "Cancel", style: "cancel" },
    ]);
  }, [profileId]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!initialLoaded) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={88}
    >
      {/* Read-only banner */}
      {roomState !== "open" && <ReadOnlyBanner state={roomState} />}

      {/* Message list */}
      <FlashList
        ref={flashListRef}
        data={messages}
        estimatedItemSize={72}
        keyExtractor={(item) => item.id}
        onScroll={handleScroll}
        scrollEventThrottle={200}
        onEndReached={loadOlder}
        onEndReachedThreshold={0.3}
        ListHeaderComponent={loadingOlder ? <ActivityIndicator style={{ margin: 12 }} /> : null}
        renderItem={({ item }) => (
          <MessageBubble
            message={item}
            isSelf={item.sender_profile_id === profileId}
            isRead={
              otherReadMsgId !== null &&
              item.id <= otherReadMsgId &&
              item.sender_profile_id === profileId
            }
            onLongPress={() => handleLongPress(item)}
            onReplyPress={() => setReplyTo(item)}
          />
        )}
        ListFooterComponent={isOtherTyping ? <TypingIndicator /> : null}
        contentContainerStyle={styles.listContent}
      />

      {/* New messages badge */}
      {newMsgCount > 0 && (
        <TouchableOpacity style={styles.newMsgBadge} onPress={handleScrollToBottom}>
          <Text style={styles.newMsgText}>{newMsgCount} new message{newMsgCount > 1 ? "s" : ""} ↓</Text>
        </TouchableOpacity>
      )}

      {/* Reply preview bar */}
      {replyTo && (
        <View style={styles.replyBar}>
          <Text style={styles.replyLabel} numberOfLines={1}>
            Replying to: {replyTo.body ?? "[media]"}
          </Text>
          <TouchableOpacity onPress={() => setReplyTo(null)}>
            <Text style={styles.replyCancel}>✕</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Composer */}
      {roomState === "open" && (
        <MessageComposer
          roomId={roomId}
          onSendText={handleSend}
          onTypingStart={() => sendTyping("start")}
          onTypingStop={() => sendTyping("stop")}
          disabled={!isConnected}
        />
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F9F9F9" },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  listContent: { paddingHorizontal: 12, paddingBottom: 8 },
  newMsgBadge: {
    position: "absolute",
    bottom: 80,
    alignSelf: "center",
    backgroundColor: "#007AFF",
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  newMsgText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  replyBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#F0F0F0",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: "#DDD",
  },
  replyLabel: { flex: 1, fontSize: 13, color: "#555" },
  replyCancel: { fontSize: 16, color: "#999", paddingLeft: 8 },
});
