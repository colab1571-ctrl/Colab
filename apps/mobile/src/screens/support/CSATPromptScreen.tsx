/**
 * CSATPromptScreen — Post-resolution satisfaction rating (1–5).
 *
 * POST /v1/support/tickets/{id}/csat
 * Handles 409 (already submitted) gracefully.
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useAuthStore } from "../../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

const STARS = [1, 2, 3, 4, 5] as const;

interface Props {
  navigation: {
    goBack: () => void;
  };
  route: {
    params: { ticketId: string };
  };
}

export function CSATPromptScreen({ navigation, route }: Props): React.ReactElement {
  const { access_token } = useAuthStore();
  const { ticketId } = route.params;

  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const handleSubmit = async () => {
    if (!score) return;
    setLoading(true);
    setError(null);

    try {
      const resp = await fetch(`${BASE_URL}/v1/support/tickets/${ticketId}/csat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access_token}`,
        },
        body: JSON.stringify({ score, comment: comment.trim() || undefined }),
      });

      if (resp.status === 409) {
        // Already submitted — treat as success
        setDone(true);
        return;
      }

      if (!resp.ok) throw new Error("Failed to submit rating");
      setDone(true);
    } catch {
      setError("Failed to submit your rating. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <View className="flex-1 bg-white items-center justify-center px-6">
        <Text className="text-4xl mb-4">🙏</Text>
        <Text className="text-xl font-bold text-neutral-900 mb-2">Thank you!</Text>
        <Text className="text-neutral-500 text-center mb-6">
          Your feedback helps us improve our support.
        </Text>
        <TouchableOpacity
          className="bg-blue-600 rounded-lg px-8 py-3"
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
        >
          <Text className="text-white font-semibold">Done</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View className="flex-1 bg-white px-6 pt-12">
      <Text className="text-xl font-bold text-neutral-900 text-center mb-2">
        How did we do?
      </Text>
      <Text className="text-neutral-500 text-center mb-8">
        Rate your support experience
      </Text>

      {/* Star rating */}
      <View className="flex-row justify-center gap-3 mb-8">
        {STARS.map((star) => (
          <TouchableOpacity
            key={star}
            onPress={() => setScore(star)}
            accessibilityRole="radio"
            accessibilityState={{ checked: score === star }}
            accessibilityLabel={`${star} star${star !== 1 ? "s" : ""}`}
          >
            <Text
              className={`text-4xl ${
                score !== null && score >= star ? "text-yellow-400" : "text-neutral-300"
              }`}
            >
              ★
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {score !== null && (
        <>
          {/* Optional comment */}
          <Text className="text-sm font-medium text-neutral-700 mb-2">
            Additional comments (optional)
          </Text>
          <TextInput
            className="border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900 h-24 mb-6"
            placeholder="Tell us more about your experience…"
            value={comment}
            onChangeText={setComment}
            multiline
            textAlignVertical="top"
            maxLength={1000}
            accessibilityLabel="CSAT comment"
          />

          {error && (
            <Text className="text-red-600 text-sm mb-4 text-center">{error}</Text>
          )}

          <TouchableOpacity
            className={`rounded-lg py-3 items-center ${loading ? "bg-neutral-300" : "bg-blue-600"}`}
            onPress={handleSubmit}
            disabled={loading}
            accessibilityRole="button"
            accessibilityLabel="Submit rating"
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text className="text-white font-semibold text-base">Submit Rating</Text>
            )}
          </TouchableOpacity>
        </>
      )}

      <TouchableOpacity
        className="mt-4 items-center"
        onPress={() => navigation.goBack()}
        accessibilityRole="button"
      >
        <Text className="text-neutral-400 text-sm">Skip</Text>
      </TouchableOpacity>
    </View>
  );
}
