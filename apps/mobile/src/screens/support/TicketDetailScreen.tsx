/**
 * TicketDetailScreen — View ticket details, event thread, and reply.
 *
 * GET  /v1/support/tickets/{id}
 * POST /v1/support/tickets/{id}/reply
 *
 * Shows CSAT prompt if ticket status is 'resolved' and no CSAT submitted yet.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useAuthStore } from "../../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

interface TicketEvent {
  id: string;
  kind: string;
  actor: string;
  body: string | null;
  created_at: string;
}

interface Ticket {
  id: string;
  category: string;
  subject: string;
  body: string;
  status: string;
  priority: string;
  sla_ack_due: string;
  sla_resolve_due: string;
  created_at: string;
}

interface Props {
  navigation: {
    navigate: (screen: string, params?: Record<string, unknown>) => void;
    goBack: () => void;
  };
  route: {
    params: { ticketId: string };
  };
}

export function TicketDetailScreen({ navigation, route }: Props): React.ReactElement {
  const { access_token } = useAuthStore();
  const { ticketId } = route.params;

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [replyBody, setReplyBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  const fetchTicket = useCallback(async () => {
    try {
      const resp = await fetch(`${BASE_URL}/v1/support/tickets/${ticketId}`, {
        headers: { Authorization: `Bearer ${access_token}` },
      });
      if (!resp.ok) throw new Error("Failed to load ticket");
      const data = await resp.json();
      setTicket(data.ticket);
      setEvents(data.events);
    } catch {
      setError("Unable to load ticket.");
    } finally {
      setLoading(false);
    }
  }, [ticketId, access_token]);

  useEffect(() => {
    fetchTicket();
  }, [fetchTicket]);

  const handleReply = async () => {
    if (!replyBody.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch(`${BASE_URL}/v1/support/tickets/${ticketId}/reply`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access_token}`,
        },
        body: JSON.stringify({ body: replyBody.trim() }),
      });
      if (!resp.ok) throw new Error("Failed to post reply");
      setReplyBody("");
      await fetchTicket();
      scrollRef.current?.scrollToEnd({ animated: true });
    } catch {
      setError("Failed to post reply. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <View className="flex-1 bg-white items-center justify-center">
        <ActivityIndicator size="large" color="#2563EB" />
      </View>
    );
  }

  if (!ticket) {
    return (
      <View className="flex-1 bg-white items-center justify-center px-6">
        <Text className="text-neutral-500 text-center">{error ?? "Ticket not found."}</Text>
        <TouchableOpacity className="mt-4" onPress={() => navigation.goBack()}>
          <Text className="text-blue-600">Go back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const showCSAT = ticket.status === "resolved";

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-white"
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      <ScrollView ref={scrollRef} contentContainerStyle={{ padding: 16 }}>
        {/* Ticket header */}
        <Text className="text-lg font-bold text-neutral-900 mb-1">{ticket.subject}</Text>
        <Text className="text-xs text-neutral-400 mb-4 capitalize">
          {ticket.category.replace(/_/g, " ")} · {ticket.status.replace(/_/g, " ")}
        </Text>

        {/* Original message */}
        <View className="bg-neutral-50 rounded-xl p-4 mb-4">
          <Text className="text-sm text-neutral-700 leading-5">{ticket.body}</Text>
        </View>

        {/* Events */}
        {events
          .filter((e) => e.kind === "reply" && e.body)
          .map((event) => (
            <View
              key={event.id}
              className={`rounded-xl p-4 mb-3 ${
                event.actor === "agent" ? "bg-blue-50 ml-4" : "bg-neutral-50 mr-4"
              }`}
            >
              <Text className="text-xs text-neutral-400 mb-1 capitalize">{event.actor}</Text>
              <Text className="text-sm text-neutral-800 leading-5">{event.body}</Text>
            </View>
          ))}

        {/* CSAT prompt */}
        {showCSAT && (
          <TouchableOpacity
            className="bg-green-50 border border-green-200 rounded-xl p-4 mb-4 items-center"
            onPress={() => navigation.navigate("CSATPrompt", { ticketId })}
            accessibilityRole="button"
            accessibilityLabel="Rate this support experience"
          >
            <Text className="text-green-700 font-semibold mb-1">
              Your ticket was resolved!
            </Text>
            <Text className="text-green-600 text-sm">Tap to rate your experience</Text>
          </TouchableOpacity>
        )}

        {error && (
          <Text className="text-red-600 text-sm mb-3">{error}</Text>
        )}
      </ScrollView>

      {/* Reply box (only for non-closed tickets) */}
      {!["resolved", "closed"].includes(ticket.status) && (
        <View className="px-4 py-3 border-t border-neutral-200 flex-row items-end gap-2">
          <TextInput
            className="flex-1 bg-neutral-100 rounded-2xl px-4 py-2 text-sm text-neutral-900 max-h-24"
            placeholder="Add a reply…"
            value={replyBody}
            onChangeText={setReplyBody}
            multiline
            maxLength={8000}
            accessibilityLabel="Reply text input"
          />
          <TouchableOpacity
            className={`w-10 h-10 rounded-full items-center justify-center ${
              submitting || !replyBody.trim() ? "bg-neutral-200" : "bg-blue-600"
            }`}
            onPress={handleReply}
            disabled={submitting || !replyBody.trim()}
            accessibilityRole="button"
            accessibilityLabel="Send reply"
          >
            {submitting ? (
              <ActivityIndicator size="small" color="#9CA3AF" />
            ) : (
              <Text className="text-white font-bold">↑</Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}
