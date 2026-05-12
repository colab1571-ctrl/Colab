import React, { useCallback, useState } from "react";
import {
  Alert,
  Modal,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";

type FeedbackTarget = "project" | "partner";
type FeedbackRating = "up" | "down";

interface TagChip {
  value: string;
  label: string;
  forTarget: FeedbackTarget | "both";
}

const TAG_CHIPS: TagChip[] = [
  // Partner tags
  { value: "communicative", label: "Communicative", forTarget: "partner" },
  { value: "responsive", label: "Responsive", forTarget: "partner" },
  { value: "professional", label: "Professional", forTarget: "partner" },
  { value: "creative", label: "Creative", forTarget: "partner" },
  { value: "reliable", label: "Reliable", forTarget: "partner" },
  { value: "flexible", label: "Flexible", forTarget: "partner" },
  { value: "ghosted", label: "Ghosted Me", forTarget: "partner" },
  { value: "slow_to_respond", label: "Slow to Respond", forTarget: "partner" },
  { value: "missed_deadlines", label: "Missed Deadlines", forTarget: "partner" },
  { value: "scope_creep", label: "Scope Creep", forTarget: "partner" },
  // Project tags
  { value: "great_outcome", label: "Great Outcome", forTarget: "project" },
  { value: "met_goals", label: "Met Goals", forTarget: "project" },
  { value: "learned_a_lot", label: "Learned a Lot", forTarget: "project" },
  { value: "good_creative_fit", label: "Good Creative Fit", forTarget: "project" },
  { value: "incomplete", label: "Incomplete", forTarget: "project" },
  { value: "unclear_direction", label: "Unclear Direction", forTarget: "project" },
  { value: "changed_scope", label: "Changed Scope", forTarget: "project" },
  { value: "technical_issues", label: "Technical Issues", forTarget: "project" },
];

interface FeedbackFormProps {
  target: FeedbackTarget;
  collabId: string;
  onSuccess: () => void;
}

function FeedbackForm({
  target,
  collabId,
  onSuccess,
}: FeedbackFormProps): React.ReactElement {
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const relevantTags = TAG_CHIPS.filter(
    (t) => t.forTarget === target || t.forTarget === "both"
  );

  const toggleTag = useCallback((tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!rating) {
      Alert.alert("Please select a rating (thumbs up or down).");
      return;
    }
    setSubmitting(true);
    try {
      const resp = await fetch(`/collabs/${collabId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target,
          rating,
          tags: Array.from(selectedTags),
          comment: comment.trim() || null,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        Alert.alert("Error", err.detail?.error_code ?? "Failed to submit feedback");
        return;
      }
      onSuccess();
    } catch (e) {
      Alert.alert("Error", (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }, [rating, collabId, target, selectedTags, comment, onSuccess]);

  return (
    <View className="mt-4">
      {/* Thumbs up / down */}
      <Text className="text-sm font-semibold text-neutral-700 mb-3">
        Overall {target === "partner" ? "Partner" : "Project"} Rating
      </Text>
      <View className="flex-row gap-3 mb-4">
        <Pressable
          onPress={() => setRating("up")}
          className={`flex-1 py-3 rounded-xl border-2 items-center ${
            rating === "up"
              ? "border-green-500 bg-green-50"
              : "border-neutral-200 bg-white"
          }`}
        >
          <Text className="text-2xl">👍</Text>
          <Text
            className={`text-sm font-medium mt-1 ${
              rating === "up" ? "text-green-700" : "text-neutral-500"
            }`}
          >
            Thumbs Up
          </Text>
        </Pressable>
        <Pressable
          onPress={() => setRating("down")}
          className={`flex-1 py-3 rounded-xl border-2 items-center ${
            rating === "down"
              ? "border-red-400 bg-red-50"
              : "border-neutral-200 bg-white"
          }`}
        >
          <Text className="text-2xl">👎</Text>
          <Text
            className={`text-sm font-medium mt-1 ${
              rating === "down" ? "text-red-600" : "text-neutral-500"
            }`}
          >
            Thumbs Down
          </Text>
        </Pressable>
      </View>

      {/* Tag chips */}
      <Text className="text-sm font-semibold text-neutral-700 mb-2">
        Tags (optional)
      </Text>
      <View className="flex-row flex-wrap gap-2 mb-4">
        {relevantTags.map((chip) => (
          <Pressable
            key={chip.value}
            onPress={() => toggleTag(chip.value)}
            className={`px-3 py-1.5 rounded-full border ${
              selectedTags.has(chip.value)
                ? "border-indigo-500 bg-indigo-50"
                : "border-neutral-200 bg-white"
            }`}
          >
            <Text
              className={`text-sm ${
                selectedTags.has(chip.value)
                  ? "text-indigo-700 font-medium"
                  : "text-neutral-600"
              }`}
            >
              {chip.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {/* Comment */}
      <Text className="text-sm font-semibold text-neutral-700 mb-2">
        Comment (optional, 500 chars max)
      </Text>
      <TextInput
        value={comment}
        onChangeText={setComment}
        maxLength={500}
        multiline
        numberOfLines={3}
        placeholder="Share more about your experience..."
        placeholderTextColor="#9ca3af"
        className="border border-neutral-200 rounded-xl p-3 text-neutral-900 text-sm bg-white min-h-20"
      />
      <Text className="text-xs text-neutral-400 text-right mt-1">
        {comment.length}/500
      </Text>

      {/* Submit */}
      <Pressable
        onPress={handleSubmit}
        disabled={submitting}
        className={`mt-4 py-3 rounded-xl items-center ${
          submitting ? "bg-indigo-300" : "bg-indigo-600"
        }`}
      >
        <Text className="text-white font-semibold">
          {submitting ? "Submitting..." : "Submit Feedback"}
        </Text>
      </Pressable>
    </View>
  );
}

interface FeedbackPromptModalProps {
  visible: boolean;
  collabId: string;
  onDismiss: () => void;
}

export function FeedbackPromptModal({
  visible,
  collabId,
  onDismiss,
}: FeedbackPromptModalProps): React.ReactElement {
  const [activeTarget, setActiveTarget] = useState<FeedbackTarget>("partner");
  const [partnerDone, setPartnerDone] = useState(false);
  const [projectDone, setProjectDone] = useState(false);

  const allDone = partnerDone && projectDone;

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onDismiss}
    >
      <View className="flex-1 bg-neutral-50">
        {/* Header */}
        <View className="bg-white px-4 pt-6 pb-4 border-b border-neutral-100">
          <View className="flex-row items-center justify-between">
            <Text className="text-lg font-bold text-neutral-900">
              Share Your Feedback
            </Text>
            <Pressable onPress={onDismiss}>
              <Text className="text-indigo-600 font-medium">
                {allDone ? "Done" : "Skip"}
              </Text>
            </Pressable>
          </View>
          <Text className="text-sm text-neutral-500 mt-1">
            Rate separately for the project and your partner.
          </Text>

          {/* Target tabs */}
          <View className="flex-row mt-4 bg-neutral-100 rounded-xl p-1">
            {(["partner", "project"] as FeedbackTarget[]).map((t) => (
              <Pressable
                key={t}
                onPress={() => setActiveTarget(t)}
                className={`flex-1 py-2 rounded-lg items-center ${
                  activeTarget === t ? "bg-white shadow-sm" : ""
                }`}
              >
                <Text
                  className={`text-sm font-medium ${
                    activeTarget === t ? "text-neutral-900" : "text-neutral-400"
                  }`}
                >
                  {t === "partner" ? "Partner" : "Project"}
                  {t === "partner" && partnerDone ? " ✓" : ""}
                  {t === "project" && projectDone ? " ✓" : ""}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        <ScrollView className="flex-1 px-4">
          {activeTarget === "partner" && !partnerDone && (
            <FeedbackForm
              key="partner"
              target="partner"
              collabId={collabId}
              onSuccess={() => {
                setPartnerDone(true);
                if (!projectDone) setActiveTarget("project");
              }}
            />
          )}
          {activeTarget === "project" && !projectDone && (
            <FeedbackForm
              key="project"
              target="project"
              collabId={collabId}
              onSuccess={() => {
                setProjectDone(true);
                if (!partnerDone) setActiveTarget("partner");
              }}
            />
          )}
          {activeTarget === "partner" && partnerDone && (
            <View className="items-center py-8">
              <Text className="text-4xl">✓</Text>
              <Text className="text-neutral-600 mt-2">Partner feedback submitted!</Text>
            </View>
          )}
          {activeTarget === "project" && projectDone && (
            <View className="items-center py-8">
              <Text className="text-4xl">✓</Text>
              <Text className="text-neutral-600 mt-2">Project feedback submitted!</Text>
            </View>
          )}
          <View className="h-8" />
        </ScrollView>
      </View>
    </Modal>
  );
}
