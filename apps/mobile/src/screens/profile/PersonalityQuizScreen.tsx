/**
 * Personality Quiz — 6 weighted questions → 8 archetype enum.
 *
 * Optional flow. Results posted to POST /api/v1/profile/me/personality.
 * Target ≤90 seconds.
 */

import React, { useState } from "react";
import {
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ScrollView,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

type Props = {
  navigation: NativeStackNavigationProp<any, "PersonalityQuiz">;
};

interface Question {
  question_key: string;
  prompt: string;
  options: { answer_key: string; label: string }[];
}

// Questions loaded from /api/v1/vocations/taxonomy or baked in from seed
const QUESTIONS: Question[] = [
  {
    question_key: "work_pace",
    prompt: "When you're deep in a project, you…",
    options: [
      { answer_key: "a", label: "plan every beat ahead" },
      { answer_key: "b", label: "ride the wave and edit later" },
      { answer_key: "c", label: "ship a draft, then obsess" },
      { answer_key: "d", label: "need a collaborator in the room" },
    ],
  },
  {
    question_key: "feedback_style",
    prompt: "Best feedback you ever got was…",
    options: [
      { answer_key: "a", label: "brutally specific" },
      { answer_key: "b", label: "emotionally validating" },
      { answer_key: "c", label: "one provocative question" },
      { answer_key: "d", label: "'I'd buy this'" },
    ],
  },
  {
    question_key: "risk_appetite",
    prompt: "You'd rather…",
    options: [
      { answer_key: "a", label: "nail what you know" },
      { answer_key: "b", label: "invent a new lane" },
      { answer_key: "c", label: "translate between worlds" },
      { answer_key: "d", label: "scale what works" },
    ],
  },
  {
    question_key: "collab_role",
    prompt: "In a duo, you naturally…",
    options: [
      { answer_key: "a", label: "set the vision" },
      { answer_key: "b", label: "hold the room together" },
      { answer_key: "c", label: "push the weird" },
      { answer_key: "d", label: "polish the output" },
    ],
  },
  {
    question_key: "success_metric",
    prompt: "A project is 'done' when…",
    options: [
      { answer_key: "a", label: "it's perfect" },
      { answer_key: "b", label: "it moves someone" },
      { answer_key: "c", label: "people are using it" },
      { answer_key: "d", label: "it changed your mind" },
    ],
  },
  {
    question_key: "energy_source",
    prompt: "You're recharged by…",
    options: [
      { answer_key: "a", label: "solitude + a notebook" },
      { answer_key: "b", label: "a packed studio session" },
      { answer_key: "c", label: "blueprint + spreadsheets" },
      { answer_key: "d", label: "an argument worth having" },
    ],
  },
];

const ARCHETYPE_LABELS: Record<string, string> = {
  architect: "The Architect",
  craftsperson: "The Craftsperson",
  mystic: "The Mystic",
  maverick: "The Maverick",
  connector: "The Connector",
  storyteller: "The Storyteller",
  producer: "The Producer",
  showrunner: "The Showrunner",
};

export function PersonalityQuizScreen({ navigation }: Props): React.ReactElement {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{ archetype: string; scores: Record<string, number> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectAnswer = (questionKey: string, answerKey: string) => {
    setAnswers((prev) => ({ ...prev, [questionKey]: answerKey }));
  };

  const allAnswered = QUESTIONS.every((q) => answers[q.question_key]);

  const handleSubmit = async () => {
    if (!allAnswered) {
      setError("Please answer all questions.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = {
        answers: QUESTIONS.map((q) => ({
          question_key: q.question_key,
          answer_key: answers[q.question_key],
        })),
      };
      // TODO: const res = await profileApi.submitPersonality(payload);
      // setResult(res);
      // Stub result for now
      setResult({ archetype: "architect", scores: {} });
    } catch (e: any) {
      setError(e.message || "Failed to score quiz.");
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <View style={styles.resultContainer}>
        <Text style={styles.resultHeading}>You're</Text>
        <Text style={styles.archetype}>{ARCHETYPE_LABELS[result.archetype] || result.archetype}</Text>
        <Text style={styles.resultSubtext}>
          This archetype will subtly influence your matches. You can retake the quiz any time.
        </Text>
        <TouchableOpacity
          style={styles.nextBtn}
          onPress={() => navigation.navigate("OAuthConnect" as never)}
        >
          <Text style={styles.nextBtnText}>Connect socials (optional)</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.skipBtn}
          onPress={() => navigation.navigate("ProfileView" as never)}
        >
          <Text style={styles.skipBtnText}>Skip</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>What kind of creator are you?</Text>
      <Text style={styles.subheading}>6 questions. ~90 seconds. Completely optional.</Text>

      {QUESTIONS.map((q, idx) => (
        <View key={q.question_key} style={styles.questionBlock}>
          <Text style={styles.questionNumber}>Q{idx + 1}</Text>
          <Text style={styles.questionPrompt}>{q.prompt}</Text>
          {q.options.map((opt) => {
            const selected = answers[q.question_key] === opt.answer_key;
            return (
              <TouchableOpacity
                key={opt.answer_key}
                style={[styles.optionBtn, selected && styles.optionBtnSelected]}
                onPress={() => selectAnswer(q.question_key, opt.answer_key)}
              >
                <Text style={[styles.optionText, selected && styles.optionTextSelected]}>
                  {opt.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      ))}

      {error && <Text style={styles.error}>{error}</Text>}

      <TouchableOpacity
        style={[styles.nextBtn, (!allAnswered || loading) && styles.nextBtnDisabled]}
        onPress={handleSubmit}
        disabled={!allAnswered || loading}
      >
        <Text style={styles.nextBtnText}>{loading ? "Scoring…" : "See my archetype"}</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.skipBtn}
        onPress={() => navigation.navigate("OAuthConnect" as never)}
      >
        <Text style={styles.skipBtnText}>Skip quiz</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  content: { padding: 24, paddingBottom: 48 },
  heading: { fontSize: 24, fontWeight: "700", marginBottom: 8 },
  subheading: { fontSize: 14, color: "#666", marginBottom: 24 },
  questionBlock: { marginBottom: 24 },
  questionNumber: { fontSize: 11, color: "#999", marginBottom: 4 },
  questionPrompt: { fontSize: 18, fontWeight: "600", marginBottom: 12 },
  optionBtn: {
    padding: 14, borderRadius: 10, borderWidth: 1, borderColor: "#ddd", marginBottom: 8,
  },
  optionBtnSelected: { backgroundColor: "#000", borderColor: "#000" },
  optionText: { fontSize: 15, color: "#333" },
  optionTextSelected: { color: "#fff" },
  nextBtn: {
    backgroundColor: "#000", borderRadius: 12, padding: 16,
    alignItems: "center", marginTop: 16,
  },
  nextBtnDisabled: { opacity: 0.4 },
  nextBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  skipBtn: { alignItems: "center", marginTop: 12, padding: 8 },
  skipBtnText: { color: "#999", fontSize: 14 },
  resultContainer: { flex: 1, backgroundColor: "#fff", padding: 32, justifyContent: "center", alignItems: "center" },
  resultHeading: { fontSize: 18, color: "#666", marginBottom: 4 },
  archetype: { fontSize: 36, fontWeight: "700", textAlign: "center", marginBottom: 16 },
  resultSubtext: { fontSize: 14, color: "#666", textAlign: "center", marginBottom: 32 },
  error: { color: "red", marginVertical: 8, textAlign: "center" },
});
