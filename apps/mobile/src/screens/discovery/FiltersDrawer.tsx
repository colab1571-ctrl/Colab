/**
 * FiltersDrawer — slide-up drawer for feed filter controls.
 *
 * Spec FR-B-4 filter fields:
 *  - Vocation category (multi-select from 9 categories)
 *  - Location radius (slider: 10–500 km or mi, or "Anywhere")
 *  - Experience level (min–max range: 1–5)
 *  - Open to remote (toggle)
 *  - Last active (dropdown: 7d / 30d / 90d)
 *  - Minimum successful collabs (0–10)
 *
 * NOTE: Profile health score is NEVER exposed as a filter (spec §0, plan §5.3).
 * Client-side 400ms debounce is handled by the parent FeedScreen.
 */

import React, { useState } from "react";
import {
  Modal,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { type FeedFilters } from "../../api/discovery";

const VOCATION_CATEGORIES = [
  "Visual Arts",
  "Performing Arts",
  "Literary Arts",
  "Music",
  "Film/Video",
  "Design",
  "Digital/Tech",
  "Media & Journalism",
  "Craft & Maker",
];

const LAST_ACTIVE_OPTIONS = [
  { label: "Last 7 days", value: 7 },
  { label: "Last 30 days", value: 30 },
  { label: "Last 90 days", value: 90 },
];

const EXPERIENCE_LABELS: Record<number, string> = {
  1: "Beginner",
  2: "Developing",
  3: "Intermediate",
  4: "Advanced",
  5: "Expert",
};

interface Props {
  visible: boolean;
  filters: FeedFilters;
  onApply: (filters: FeedFilters) => void;
  onClose: () => void;
}

export function FiltersDrawer({ visible, filters, onApply, onClose }: Props): React.ReactElement {
  const [local, setLocal] = useState<FeedFilters>(filters);

  const toggleVocation = (cat: string) => {
    const current = local.vocation_categories ?? [];
    const next = current.includes(cat)
      ? current.filter((c) => c !== cat)
      : [...current, cat];
    setLocal({ ...local, vocation_categories: next });
  };

  const reset = () => setLocal({});

  const apply = () => onApply(local);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose}>
            <Text style={styles.cancelText}>Cancel</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Filters</Text>
          <TouchableOpacity onPress={reset}>
            <Text style={styles.resetText}>Reset</Text>
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          {/* Vocation categories */}
          <Text style={styles.sectionLabel}>Creative Roles</Text>
          <View style={styles.chipsGrid}>
            {VOCATION_CATEGORIES.map((cat) => {
              const selected = (local.vocation_categories ?? []).includes(cat);
              return (
                <TouchableOpacity
                  key={cat}
                  style={[styles.chip, selected && styles.chipSelected]}
                  onPress={() => toggleVocation(cat)}
                >
                  <Text style={[styles.chipText, selected && styles.chipTextSelected]}>
                    {cat}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Anywhere toggle */}
          <View style={styles.rowControl}>
            <View>
              <Text style={styles.controlLabel}>Anywhere (no radius)</Text>
              <Text style={styles.controlSub}>Show profiles from all locations</Text>
            </View>
            <Switch
              value={local.anywhere ?? false}
              onValueChange={(v) => setLocal({ ...local, anywhere: v, radius_km: v ? undefined : local.radius_km })}
              trackColor={{ true: "#5B5BD6" }}
            />
          </View>

          {/* Radius — only shown when not "anywhere" */}
          {!local.anywhere && (
            <View style={styles.controlBlock}>
              <Text style={styles.controlLabel}>Radius</Text>
              <View style={styles.radiusOptions}>
                {[25, 50, 100, 250].map((r) => (
                  <TouchableOpacity
                    key={r}
                    style={[styles.radiusChip, local.radius_km === r && styles.chipSelected]}
                    onPress={() => setLocal({ ...local, radius_km: r })}
                  >
                    <Text style={[styles.chipText, local.radius_km === r && styles.chipTextSelected]}>
                      {r} km
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {/* Experience level */}
          <View style={styles.controlBlock}>
            <Text style={styles.controlLabel}>Experience Level</Text>
            <View style={styles.expRow}>
              {[1, 2, 3, 4, 5].map((lvl) => {
                const isMin = local.experience_level_min === lvl;
                const isMax = local.experience_level_max === lvl;
                const inRange =
                  (local.experience_level_min ?? 1) <= lvl &&
                  lvl <= (local.experience_level_max ?? 5);
                return (
                  <TouchableOpacity
                    key={lvl}
                    style={[styles.expChip, inRange && styles.chipSelected]}
                    onPress={() => {
                      if (!local.experience_level_min || lvl < local.experience_level_min) {
                        setLocal({ ...local, experience_level_min: lvl });
                      } else {
                        setLocal({ ...local, experience_level_max: lvl });
                      }
                    }}
                  >
                    <Text style={[styles.chipText, inRange && styles.chipTextSelected]}>
                      {lvl}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <Text style={styles.controlSub}>
              {local.experience_level_min
                ? `${EXPERIENCE_LABELS[local.experience_level_min]} → ${EXPERIENCE_LABELS[local.experience_level_max ?? 5]}`
                : "All levels"}
            </Text>
          </View>

          {/* Open to remote */}
          <View style={styles.rowControl}>
            <Text style={styles.controlLabel}>Open to remote only</Text>
            <Switch
              value={local.open_to_remote ?? false}
              onValueChange={(v) => setLocal({ ...local, open_to_remote: v || undefined })}
              trackColor={{ true: "#5B5BD6" }}
            />
          </View>

          {/* Last active */}
          <View style={styles.controlBlock}>
            <Text style={styles.controlLabel}>Last Active</Text>
            <View style={styles.chipsGrid}>
              {LAST_ACTIVE_OPTIONS.map(({ label, value }) => (
                <TouchableOpacity
                  key={value}
                  style={[styles.chip, local.last_active_days === value && styles.chipSelected]}
                  onPress={() => setLocal({ ...local, last_active_days: value })}
                >
                  <Text style={[styles.chipText, local.last_active_days === value && styles.chipTextSelected]}>
                    {label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Min collabs */}
          <View style={styles.controlBlock}>
            <Text style={styles.controlLabel}>Minimum Collabs</Text>
            <View style={styles.chipsGrid}>
              {[0, 1, 3, 5].map((n) => (
                <TouchableOpacity
                  key={n}
                  style={[styles.chip, (local.min_successful_collabs ?? 0) === n && styles.chipSelected]}
                  onPress={() => setLocal({ ...local, min_successful_collabs: n })}
                >
                  <Text style={[styles.chipText, (local.min_successful_collabs ?? 0) === n && styles.chipTextSelected]}>
                    {n === 0 ? "Any" : `${n}+`}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </ScrollView>

        {/* Apply */}
        <View style={styles.footer}>
          <TouchableOpacity style={styles.applyBtn} onPress={apply}>
            <Text style={styles.applyText}>Show Results</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FAFAFA" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 16,
    paddingTop: 20,
    backgroundColor: "#fff",
    borderBottomColor: "#E0E0E0",
    borderBottomWidth: 1,
  },
  cancelText: { fontSize: 16, color: "#8A8A8A" },
  title: { fontSize: 17, fontWeight: "700", color: "#1A1A1A" },
  resetText: { fontSize: 16, color: "#5B5BD6" },
  content: { padding: 16, paddingBottom: 100 },
  sectionLabel: {
    fontSize: 12,
    fontWeight: "700",
    color: "#A0A0A0",
    textTransform: "uppercase",
    marginBottom: 10,
    marginTop: 8,
  },
  controlLabel: { fontSize: 15, fontWeight: "600", color: "#1A1A1A", marginBottom: 4 },
  controlSub: { fontSize: 12, color: "#A0A0A0", marginTop: 4 },
  controlBlock: { marginBottom: 24 },
  rowControl: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
    borderColor: "#E8E8E8",
    borderWidth: 1,
  },
  chipsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 16,
    borderColor: "#E0E0E0",
    borderWidth: 1,
    backgroundColor: "#fff",
  },
  chipSelected: { backgroundColor: "#5B5BD6", borderColor: "#5B5BD6" },
  chipText: { fontSize: 13, color: "#4A4A4A" },
  chipTextSelected: { color: "#fff", fontWeight: "600" },
  radiusOptions: { flexDirection: "row", gap: 8, marginTop: 4 },
  radiusChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 12,
    borderColor: "#E0E0E0",
    borderWidth: 1,
    backgroundColor: "#fff",
  },
  expRow: { flexDirection: "row", gap: 8, marginTop: 4, marginBottom: 6 },
  expChip: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 22,
    borderColor: "#E0E0E0",
    borderWidth: 1,
    backgroundColor: "#fff",
  },
  footer: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: 16,
    paddingBottom: 32,
    backgroundColor: "#fff",
    borderTopColor: "#E0E0E0",
    borderTopWidth: 1,
  },
  applyBtn: {
    backgroundColor: "#5B5BD6",
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: "center",
  },
  applyText: { fontSize: 16, fontWeight: "700", color: "#fff" },
});
