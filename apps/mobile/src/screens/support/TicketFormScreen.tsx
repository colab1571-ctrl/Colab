/**
 * TicketFormScreen — Create a new support ticket.
 *
 * POST /v1/support/tickets
 * Pre-populates category from chatbot hand-off suggestedCategory param.
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useAuthStore } from "../../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

const CATEGORIES = [
  { value: "harassment_threats", label: "Harassment / Threats" },
  { value: "ip_dmca", label: "IP / DMCA" },
  { value: "payment", label: "Payment Issue" },
  { value: "technical", label: "Technical Problem" },
  { value: "other", label: "Other" },
] as const;

type Category = (typeof CATEGORIES)[number]["value"];

interface Props {
  navigation: {
    navigate: (screen: string, params?: Record<string, unknown>) => void;
    goBack: () => void;
  };
  route?: {
    params?: { suggestedCategory?: Category };
  };
}

export function TicketFormScreen({ navigation, route }: Props): React.ReactElement {
  const { access_token } = useAuthStore();
  const [category, setCategory] = useState<Category>(
    route?.params?.suggestedCategory ?? "other"
  );
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async () => {
    if (!subject.trim() || !body.trim()) {
      setError("Please fill in both subject and description.");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const resp = await fetch(`${BASE_URL}/v1/support/tickets`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access_token}`,
        },
        body: JSON.stringify({ category, subject: subject.trim(), body: body.trim() }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Failed to create ticket");
      }

      setSuccess(true);
      setTimeout(() => navigation.navigate("TicketList"), 1500);
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message ?? "Failed to create ticket. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <View className="flex-1 bg-white items-center justify-center px-6">
        <Text className="text-3xl mb-4">✓</Text>
        <Text className="text-xl font-bold text-neutral-900 mb-2">Ticket submitted!</Text>
        <Text className="text-neutral-500 text-center">
          We'll get back to you by email. Redirecting to your tickets…
        </Text>
      </View>
    );
  }

  return (
    <ScrollView className="flex-1 bg-white" contentContainerStyle={{ padding: 16 }}>
      <Text className="text-lg font-semibold text-neutral-900 mb-4">
        Open a Support Ticket
      </Text>

      {/* Category */}
      <Text className="text-sm font-medium text-neutral-700 mb-2">Category</Text>
      <View className="flex-row flex-wrap gap-2 mb-4">
        {CATEGORIES.map((cat) => (
          <TouchableOpacity
            key={cat.value}
            className={`rounded-full px-3 py-1.5 border ${
              category === cat.value
                ? "bg-blue-600 border-blue-600"
                : "bg-white border-neutral-300"
            }`}
            onPress={() => setCategory(cat.value)}
            accessibilityRole="radio"
            accessibilityState={{ checked: category === cat.value }}
          >
            <Text
              className={`text-sm ${
                category === cat.value ? "text-white" : "text-neutral-700"
              }`}
            >
              {cat.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Subject */}
      <Text className="text-sm font-medium text-neutral-700 mb-1">Subject</Text>
      <TextInput
        className="border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900 mb-4"
        placeholder="Brief summary of your issue"
        value={subject}
        onChangeText={setSubject}
        maxLength={255}
        accessibilityLabel="Ticket subject"
      />

      {/* Body */}
      <Text className="text-sm font-medium text-neutral-700 mb-1">Description</Text>
      <TextInput
        className="border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900 mb-4 h-32"
        placeholder="Please describe your issue in detail…"
        value={body}
        onChangeText={setBody}
        multiline
        textAlignVertical="top"
        maxLength={8000}
        accessibilityLabel="Ticket description"
      />

      {error && (
        <Text className="text-red-600 text-sm mb-4">{error}</Text>
      )}

      <TouchableOpacity
        className={`rounded-lg py-3 items-center ${loading ? "bg-neutral-300" : "bg-blue-600"}`}
        onPress={handleSubmit}
        disabled={loading}
        accessibilityRole="button"
        accessibilityLabel="Submit ticket"
      >
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text className="text-white font-semibold text-base">Submit Ticket</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        className="mt-3 items-center"
        onPress={() => navigation.goBack()}
        accessibilityRole="button"
      >
        <Text className="text-neutral-500 text-sm">Cancel</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}
