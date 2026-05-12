/**
 * Vocation Picker — 9-category taxonomy with sub-tags.
 *
 * User selects up to N vocations from 9 categories + curated sub-tags.
 * One must be marked primary. Free-text "other" accepted.
 * Submits to PUT /api/v1/profile/me/vocations.
 */

import React, { useState } from "react";
import {
  FlatList,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

type Props = {
  navigation: NativeStackNavigationProp<any, "VocationPicker">;
};

interface VocationSelection {
  category: string;
  subtag: string;
  is_primary: boolean;
}

// Static taxonomy stub — loaded from /api/v1/vocations/taxonomy in production
const CATEGORIES = [
  "Visual Arts",
  "Music & Audio",
  "Performing Arts",
  "Film, Video & Animation",
  "Design",
  "Writing & Literature",
  "Digital, Code & New Media",
  "Craft, Fashion & Maker",
  "Producing, Curation & Direction",
];

export function VocationPickerScreen({ navigation }: Props): React.ReactElement {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selections, setSelections] = useState<VocationSelection[]>([]);
  const [otherText, setOtherText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleVocation = (category: string, subtag: string) => {
    const existing = selections.find((s) => s.category === category && s.subtag === subtag);
    if (existing) {
      setSelections((prev) => prev.filter((s) => !(s.category === category && s.subtag === subtag)));
    } else {
      const newSel: VocationSelection = {
        category,
        subtag,
        is_primary: selections.length === 0,
      };
      setSelections((prev) => [...prev, newSel]);
    }
  };

  const setPrimary = (category: string, subtag: string) => {
    setSelections((prev) =>
      prev.map((s) => ({
        ...s,
        is_primary: s.category === category && s.subtag === subtag,
      }))
    );
  };

  const handleSubmit = async () => {
    if (selections.length === 0) {
      setError("Please select at least one vocation.");
      return;
    }
    if (!selections.some((s) => s.is_primary)) {
      setError("Please mark one vocation as primary.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // TODO: call PUT /api/v1/profile/me/vocations with selections
      navigation.navigate("PortfolioUpload" as never);
    } catch (e: any) {
      setError(e.message || "Failed to save vocations.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>What do you create?</Text>
      <Text style={styles.subheading}>
        Pick your vocations. Star the one that defines you most.
      </Text>

      {/* Category list */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryScroll}>
        {CATEGORIES.map((cat) => (
          <TouchableOpacity
            key={cat}
            style={[styles.categoryChip, selectedCategory === cat && styles.categoryChipActive]}
            onPress={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
          >
            <Text style={[styles.categoryChipText, selectedCategory === cat && styles.categoryChipTextActive]}>
              {cat}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Selected vocations */}
      {selections.length > 0 && (
        <View style={styles.selectedSection}>
          <Text style={styles.sectionLabel}>Selected ({selections.length})</Text>
          <FlatList
            horizontal
            data={selections}
            keyExtractor={(item) => `${item.category}/${item.subtag}`}
            renderItem={({ item }) => (
              <TouchableOpacity
                style={[styles.selectedChip, item.is_primary && styles.selectedChipPrimary]}
                onLongPress={() => setPrimary(item.category, item.subtag)}
                onPress={() => toggleVocation(item.category, item.subtag)}
              >
                <Text style={[styles.selectedChipText, item.is_primary && styles.selectedChipTextPrimary]}>
                  {item.is_primary ? "★ " : ""}{item.subtag}
                </Text>
              </TouchableOpacity>
            )}
          />
          <Text style={styles.hint}>Long-press to set as primary</Text>
        </View>
      )}

      {error && <Text style={styles.error}>{error}</Text>}

      <TouchableOpacity
        style={[styles.nextBtn, loading && styles.nextBtnDisabled]}
        onPress={handleSubmit}
        disabled={loading || selections.length === 0}
      >
        <Text style={styles.nextBtnText}>Continue</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", padding: 24 },
  heading: { fontSize: 24, fontWeight: "700", marginBottom: 8 },
  subheading: { fontSize: 14, color: "#666", marginBottom: 16 },
  categoryScroll: { flexGrow: 0, marginBottom: 16 },
  categoryChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
    borderWidth: 1, borderColor: "#ddd", marginRight: 8,
  },
  categoryChipActive: { backgroundColor: "#000", borderColor: "#000" },
  categoryChipText: { fontSize: 13, color: "#333" },
  categoryChipTextActive: { color: "#fff" },
  selectedSection: { marginVertical: 12 },
  sectionLabel: { fontSize: 13, fontWeight: "600", marginBottom: 8 },
  selectedChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16,
    backgroundColor: "#f0f0f0", marginRight: 6,
  },
  selectedChipPrimary: { backgroundColor: "#000" },
  selectedChipText: { fontSize: 13, color: "#333" },
  selectedChipTextPrimary: { color: "#fff" },
  hint: { fontSize: 11, color: "#999", marginTop: 4 },
  nextBtn: {
    backgroundColor: "#000", borderRadius: 12, padding: 16,
    alignItems: "center", marginTop: "auto",
  },
  nextBtnDisabled: { opacity: 0.4 },
  nextBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  error: { color: "red", marginVertical: 8 },
});
