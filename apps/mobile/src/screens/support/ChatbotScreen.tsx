/**
 * ChatbotScreen — AI support chatbot with FAQ retrieval.
 *
 * Streams responses from POST /v1/support/chatbot (SSE).
 * Detects {"action":"create_ticket"} sentinel and navigates to ticket form.
 * Rate limit: 10 turns/hour (shows 429 gracefully).
 */

import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useAuthStore } from "../../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

interface Props {
  navigation: {
    navigate: (screen: string, params?: Record<string, unknown>) => void;
  };
  route?: {
    params?: { ticketId?: string };
  };
}

export function ChatbotScreen({ navigation, route }: Props): React.ReactElement {
  const { access_token } = useAuthStore();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm the Colab support assistant. I can help answer questions from our FAQ. What can I help you with?",
    },
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);
  const msgIdCounter = useRef(0);

  const nextId = () => {
    msgIdCounter.current += 1;
    return `msg-${msgIdCounter.current}`;
  };

  const appendAssistantDelta = useCallback((msgId: string, delta: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId ? { ...m, content: m.content + delta } : m
      )
    );
  }, []);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    setError(null);

    const userMsgId = nextId();
    const assistantMsgId = nextId();

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: text },
      { id: assistantMsgId, role: "assistant", content: "", isStreaming: true },
    ]);
    setIsStreaming(true);

    try {
      const resp = await fetch(`${BASE_URL}/v1/support/chatbot`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access_token}`,
        },
        body: JSON.stringify({
          message: text,
          session_id: sessionId ?? undefined,
          ticket_id: route?.params?.ticketId ?? undefined,
        }),
      });

      if (resp.status === 429) {
        setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
        setError(
          "You've reached the hourly chat limit. Please try again later or open a support ticket."
        );
        setIsStreaming(false);
        return;
      }

      if (!resp.ok) throw new Error("Chatbot request failed");

      const newSessionId = resp.headers.get("x-session-id");
      if (newSessionId) setSessionId(newSessionId);

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No stream reader");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.done) {
              // Stream complete
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, isStreaming: false } : m
                )
              );
            } else if (event.action === "create_ticket") {
              // Sentinel detected — navigate to ticket form
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        content: "Opening a support ticket for you…",
                        isStreaming: false,
                      }
                    : m
                )
              );
              setTimeout(() => {
                navigation.navigate("SupportTicketForm", {
                  suggestedCategory: event.suggested_category,
                });
              }, 800);
            } else if (event.delta) {
              appendAssistantDelta(assistantMsgId, event.delta);
            }
          } catch {
            // Malformed SSE event — skip
          }
        }
      }
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
      setError("Something went wrong. Please try again or open a support ticket.");
    } finally {
      setIsStreaming(false);
    }
  }, [input, isStreaming, sessionId, access_token, navigation, appendAssistantDelta, route]);

  const renderMessage = ({ item }: { item: Message }) => (
    <View
      className={`px-4 py-2 ${item.role === "user" ? "items-end" : "items-start"}`}
    >
      <View
        className={`max-w-xs rounded-2xl px-4 py-2 ${
          item.role === "user"
            ? "bg-blue-600"
            : "bg-neutral-100"
        }`}
      >
        <Text
          className={`text-sm leading-5 ${
            item.role === "user" ? "text-white" : "text-neutral-900"
          }`}
        >
          {item.content}
          {item.isStreaming && <Text className="text-neutral-400">▋</Text>}
        </Text>
      </View>
    </View>
  );

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-white"
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Header note */}
      <View className="px-4 py-2 bg-blue-50 border-b border-blue-100">
        <Text className="text-xs text-blue-700 text-center">
          Answers are based on our help centre articles only.
        </Text>
      </View>

      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={renderMessage}
        contentContainerStyle={{ paddingVertical: 12 }}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
      />

      {error && (
        <View className="px-4 py-2 bg-red-50 border-t border-red-100">
          <Text className="text-red-600 text-sm text-center">{error}</Text>
          <TouchableOpacity
            className="mt-1 items-center"
            onPress={() => navigation.navigate("SupportTicketForm")}
          >
            <Text className="text-blue-600 text-sm">Open a ticket instead</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Input bar */}
      <View className="px-4 py-3 border-t border-neutral-200 flex-row items-end gap-2">
        <TextInput
          className="flex-1 bg-neutral-100 rounded-2xl px-4 py-2 text-sm text-neutral-900 max-h-24"
          placeholder="Ask a question…"
          value={input}
          onChangeText={setInput}
          multiline
          maxLength={2000}
          editable={!isStreaming}
          accessibilityLabel="Chat message input"
        />
        <TouchableOpacity
          className={`w-10 h-10 rounded-full items-center justify-center ${
            isStreaming || !input.trim() ? "bg-neutral-200" : "bg-blue-600"
          }`}
          onPress={send}
          disabled={isStreaming || !input.trim()}
          accessibilityRole="button"
          accessibilityLabel="Send message"
        >
          {isStreaming ? (
            <ActivityIndicator size="small" color="#9CA3AF" />
          ) : (
            <Text className="text-white font-bold">↑</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}
