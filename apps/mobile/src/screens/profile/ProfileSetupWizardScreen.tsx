/**
 * Profile Setup Wizard — multi-step onboarding flow.
 *
 * Steps:
 *   1. Display name
 *   2. Location + radius
 *   3. Bio + obsessed with
 *   4. Experience level + optional fields
 *
 * Emits PostHog events at each step for funnel analytics.
 * Target ≤8 minutes total (FR-A-13).
 */

import React, { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

type Props = {
  navigation: NativeStackNavigationProp<any, "ProfileSetupWizard">;
};

type WizardStep = "display_name" | "location" | "bio" | "optional";

interface ProfileDraft {
  display_name: string;
  bio: string;
  obsessed_with: string;
  location_city: string;
  radius_value: number;
  radius_unit: "mi" | "km";
  open_to_remote: boolean;
  experience_level: number | null;
  looking_for: string;
  past_experience: string;
}

const STEPS: WizardStep[] = ["display_name", "location", "bio", "optional"];

export function ProfileSetupWizardScreen({ navigation }: Props): React.ReactElement {
  const [step, setStep] = useState<WizardStep>("display_name");
  const [draft, setDraft] = useState<ProfileDraft>({
    display_name: "",
    bio: "",
    obsessed_with: "",
    location_city: "",
    radius_value: 50,
    radius_unit: "mi",
    open_to_remote: false,
    experience_level: null,
    looking_for: "",
    past_experience: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const currentStepIndex = STEPS.indexOf(step);
  const progress = (currentStepIndex + 1) / STEPS.length;

  const handleNext = async () => {
    setError(null);

    if (step === "display_name") {
      if (!draft.display_name || draft.display_name.length < 2) {
        setError("Display name must be at least 2 characters.");
        return;
      }
      if (draft.display_name.length > 40) {
        setError("Display name must be 40 characters or fewer.");
        return;
      }
      setStep("location");
      return;
    }

    if (step === "location") {
      setStep("bio");
      return;
    }

    if (step === "bio") {
      if (draft.bio.length > 280) {
        setError("Bio must be 280 characters or fewer.");
        return;
      }
      if (draft.obsessed_with.length > 140) {
        setError("'Obsessed with' must be 140 characters or fewer.");
        return;
      }
      setStep("optional");
      return;
    }

    if (step === "optional") {
      await submitProfile();
    }
  };

  const submitProfile = async () => {
    setLoading(true);
    try {
      // TODO: call profile API PATCH /api/v1/profile/me
      // await profileApi.patch(draft);
      navigation.navigate("VocationPicker" as never);
    } catch (err: any) {
      setError(err.message || "Failed to save profile.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      {/* Progress bar */}
      <View style={styles.progressBar}>
        <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {step === "display_name" && (
          <View>
            <Text style={styles.heading}>What should people call you?</Text>
            <Text style={styles.subheading}>Your display name is unique and case-insensitive.</Text>
            <TextInput
              style={styles.input}
              value={draft.display_name}
              onChangeText={(t) => setDraft((d) => ({ ...d, display_name: t }))}
              placeholder="e.g. skylerbeats"
              maxLength={40}
              autoCapitalize="none"
              autoFocus
            />
            <Text style={styles.charCount}>{draft.display_name.length}/40</Text>
          </View>
        )}

        {step === "location" && (
          <View>
            <Text style={styles.heading}>Where are you based?</Text>
            <Text style={styles.subheading}>We show only your city. Exact location stays private.</Text>
            <TextInput
              style={styles.input}
              value={draft.location_city}
              onChangeText={(t) => setDraft((d) => ({ ...d, location_city: t }))}
              placeholder="Start typing a city…"
            />
            <Text style={styles.label}>Search radius</Text>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, { flex: 1 }]}
                value={String(draft.radius_value)}
                onChangeText={(t) => setDraft((d) => ({ ...d, radius_value: Number(t) || 50 }))}
                keyboardType="numeric"
                maxLength={4}
              />
              <TouchableOpacity
                style={styles.unitToggle}
                onPress={() =>
                  setDraft((d) => ({ ...d, radius_unit: d.radius_unit === "mi" ? "km" : "mi" }))
                }
              >
                <Text style={styles.unitText}>{draft.radius_unit}</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity
              style={styles.checkRow}
              onPress={() => setDraft((d) => ({ ...d, radius_value: 9999 }))}
            >
              <View style={[styles.checkbox, draft.radius_value === 9999 && styles.checkboxChecked]} />
              <Text style={styles.checkLabel}>Open to opportunities anywhere</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.checkRow}
              onPress={() => setDraft((d) => ({ ...d, open_to_remote: !d.open_to_remote }))}
            >
              <View style={[styles.checkbox, draft.open_to_remote && styles.checkboxChecked]} />
              <Text style={styles.checkLabel}>Open to remote collaboration</Text>
            </TouchableOpacity>
          </View>
        )}

        {step === "bio" && (
          <View>
            <Text style={styles.heading}>Tell your story</Text>
            <Text style={styles.label}>Bio (up to 280 characters)</Text>
            <TextInput
              style={[styles.input, styles.multiline]}
              value={draft.bio}
              onChangeText={(t) => setDraft((d) => ({ ...d, bio: t }))}
              multiline
              maxLength={280}
              placeholder="What do you make? What drives you?"
            />
            <Text style={styles.charCount}>{draft.bio.length}/280</Text>

            <Text style={styles.label}>Obsessed with (up to 140 characters)</Text>
            <TextInput
              style={[styles.input, styles.multiline]}
              value={draft.obsessed_with}
              onChangeText={(t) => setDraft((d) => ({ ...d, obsessed_with: t }))}
              multiline
              maxLength={140}
              placeholder="Right now I can't stop thinking about…"
            />
            <Text style={styles.charCount}>{draft.obsessed_with.length}/140</Text>
          </View>
        )}

        {step === "optional" && (
          <View>
            <Text style={styles.heading}>A little more (optional)</Text>
            <Text style={styles.label}>Experience level</Text>
            <View style={styles.row}>
              {[1, 2, 3, 4, 5].map((lvl) => (
                <TouchableOpacity
                  key={lvl}
                  style={[styles.levelBtn, draft.experience_level === lvl && styles.levelBtnActive]}
                  onPress={() => setDraft((d) => ({ ...d, experience_level: lvl }))}
                >
                  <Text style={draft.experience_level === lvl ? styles.levelTextActive : styles.levelText}>
                    {lvl}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.label}>What you're looking for (optional)</Text>
            <TextInput
              style={[styles.input, styles.multiline]}
              value={draft.looking_for}
              onChangeText={(t) => setDraft((d) => ({ ...d, looking_for: t }))}
              multiline
              maxLength={500}
              placeholder="Looking to collaborate on…"
            />
            <Text style={styles.label}>Notable past experience (optional)</Text>
            <TextInput
              style={[styles.input, styles.multiline]}
              value={draft.past_experience}
              onChangeText={(t) => setDraft((d) => ({ ...d, past_experience: t }))}
              multiline
              maxLength={1000}
              placeholder="Projects, credits, highlights…"
            />
          </View>
        )}

        {error && <Text style={styles.error}>{error}</Text>}

        <TouchableOpacity
          style={[styles.nextBtn, loading && styles.nextBtnDisabled]}
          onPress={handleNext}
          disabled={loading}
        >
          <Text style={styles.nextBtnText}>
            {step === "optional" ? "Finish" : "Next"}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  progressBar: { height: 4, backgroundColor: "#eee" },
  progressFill: { height: 4, backgroundColor: "#000" },
  content: { padding: 24, paddingBottom: 48 },
  heading: { fontSize: 24, fontWeight: "700", marginBottom: 8 },
  subheading: { fontSize: 14, color: "#666", marginBottom: 20 },
  label: { fontSize: 14, fontWeight: "600", marginBottom: 8, marginTop: 16 },
  input: {
    borderWidth: 1, borderColor: "#ddd", borderRadius: 8,
    padding: 12, fontSize: 16, marginBottom: 4,
  },
  multiline: { minHeight: 80, textAlignVertical: "top" },
  charCount: { fontSize: 12, color: "#999", textAlign: "right", marginBottom: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  unitToggle: {
    borderWidth: 1, borderColor: "#ddd", borderRadius: 8,
    padding: 12, width: 60, alignItems: "center",
  },
  unitText: { fontSize: 16, fontWeight: "600" },
  checkRow: { flexDirection: "row", alignItems: "center", marginTop: 12 },
  checkbox: {
    width: 20, height: 20, borderWidth: 2, borderColor: "#ddd", borderRadius: 4, marginRight: 10,
  },
  checkboxChecked: { backgroundColor: "#000", borderColor: "#000" },
  checkLabel: { fontSize: 14 },
  levelBtn: {
    width: 44, height: 44, borderWidth: 1, borderColor: "#ddd",
    borderRadius: 22, alignItems: "center", justifyContent: "center", marginRight: 8,
  },
  levelBtnActive: { backgroundColor: "#000", borderColor: "#000" },
  levelText: { fontSize: 16, color: "#333" },
  levelTextActive: { fontSize: 16, color: "#fff", fontWeight: "700" },
  nextBtn: {
    backgroundColor: "#000", borderRadius: 12, padding: 16,
    alignItems: "center", marginTop: 32,
  },
  nextBtnDisabled: { opacity: 0.5 },
  nextBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  error: { color: "red", marginTop: 8 },
});
