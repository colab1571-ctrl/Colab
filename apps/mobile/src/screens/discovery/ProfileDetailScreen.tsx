/**
 * ProfileDetailScreen — full profile view per spec FR-B-6.
 *
 * Displays:
 *  - Avatar, display name, badge state, location
 *  - Vocations, experience level, open-to-remote
 *  - Bio (280 chars), obsessed_with (140 chars)
 *  - Portfolio preview (image/video thumbnails + captions)
 *  - Collab count (anonymized saved count)
 *  - Save / Unsave action
 *  - Hide for 3 months action
 *
 * NOTE: match_score and profile_health_score are NEVER shown (spec §0 + plan §3.2).
 */

import React, { useState } from "react";
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import {
  type ProfileCard,
  hideProfile,
  saveProfile,
  unsaveProfile,
} from "../../api/discovery";
import { HideForThreeMonthsAction } from "./HideForThreeMonthsAction";

interface Props {
  profile: ProfileCard;
  onBack: () => void;
}

const EXPERIENCE_LABELS: Record<number, string> = {
  1: "Beginner",
  2: "Developing",
  3: "Intermediate",
  4: "Advanced",
  5: "Expert",
};

export function ProfileDetailScreen({ profile, onBack }: Props): React.ReactElement {
  const [saved, setSaved] = useState(profile.saved);
  const [saveLoading, setSaveLoading] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [hiddenUntil, setHiddenUntil] = useState<string | null>(null);

  const toggleSave = async () => {
    setSaveLoading(true);
    try {
      if (saved) {
        await unsaveProfile(profile.id);
        setSaved(false);
      } else {
        await saveProfile(profile.id);
        setSaved(true);
      }
    } catch {
      Alert.alert("Error", "Could not update saved status. Please try again.");
    } finally {
      setSaveLoading(false);
    }
  };

  if (hidden) {
    return (
      <View style={styles.container}>
        <TouchableOpacity style={styles.backBtn} onPress={onBack}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <View style={styles.hiddenConfirm}>
          <Text style={styles.hiddenTitle}>Profile hidden</Text>
          <Text style={styles.hiddenSubtitle}>
            {profile.display_name} won't appear in your feed
            {hiddenUntil
              ? ` until ${new Date(hiddenUntil).toLocaleDateString()}.`
              : " for 3 months."}
          </Text>
          <TouchableOpacity style={styles.backToFeedBtn} onPress={onBack}>
            <Text style={styles.backToFeedText}>Back to feed</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Nav bar */}
      <View style={styles.navBar}>
        <TouchableOpacity onPress={onBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.saveBtn, saved && styles.savedBtn]}
          onPress={toggleSave}
          disabled={saveLoading}
        >
          <Text style={[styles.saveBtnText, saved && styles.savedBtnText]}>
            {saved ? "Saved ✓" : "Save"}
          </Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Hero section */}
        <View style={styles.hero}>
          <View style={styles.avatarLarge} />
          <View style={styles.heroInfo}>
            <Text style={styles.displayName}>{profile.display_name}</Text>
            {profile.badge_state === "badge_granted" && (
              <View style={styles.badgeChip}>
                <Text style={styles.badgeText}>✦ Verified</Text>
              </View>
            )}
            {profile.location_city && (
              <Text style={styles.location}>📍 {profile.location_city}</Text>
            )}
          </View>
        </View>

        {/* Vocations */}
        {profile.vocations.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>Creative Roles</Text>
            <View style={styles.chipsRow}>
              {profile.vocations.map((v, i) => (
                <View key={i} style={styles.chip}>
                  <Text style={styles.chipText}>{v.category} · {v.subtag}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Experience + Remote */}
        <View style={styles.metaRow}>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Experience</Text>
            <Text style={styles.metaValue}>
              {EXPERIENCE_LABELS[profile.experience_level] ?? `Level ${profile.experience_level}`}
            </Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Remote</Text>
            <Text style={styles.metaValue}>
              {profile.open_to_remote ? "Open ✓" : "Local only"}
            </Text>
          </View>
          {profile.collab_count > 0 && (
            <View style={styles.metaItem}>
              <Text style={styles.metaLabel}>Collabs</Text>
              <Text style={styles.metaValue}>{profile.collab_count}</Text>
            </View>
          )}
        </View>

        {/* Bio */}
        {profile.bio && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>About</Text>
            <Text style={styles.bioText}>{profile.bio}</Text>
          </View>
        )}

        {/* Obsessed with */}
        {profile.obsessed_with && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>Obsessed with</Text>
            <Text style={styles.bioText}>{profile.obsessed_with}</Text>
          </View>
        )}

        {/* Portfolio preview */}
        {profile.portfolio_preview.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>Portfolio</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {profile.portfolio_preview.map((item, i) => (
                <View key={i} style={styles.portfolioItem}>
                  <View style={styles.portfolioThumb} />
                  {item.caption ? (
                    <Text style={styles.portfolioCaption} numberOfLines={2}>
                      {item.caption}
                    </Text>
                  ) : null}
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Last active */}
        <Text style={styles.lastActive}>Active {profile.last_active_relative}</Text>

        {/* Hide action */}
        <HideForThreeMonthsAction
          profileId={profile.id}
          displayName={profile.display_name}
          onHidden={(until) => {
            setHidden(true);
            setHiddenUntil(until);
          }}
        />
      </ScrollView>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FAFAFA" },
  navBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 56,
    paddingBottom: 12,
    backgroundColor: "#fff",
    borderBottomColor: "#E0E0E0",
    borderBottomWidth: 1,
  },
  backBtn: { padding: 8 },
  backText: { fontSize: 16, color: "#5B5BD6" },
  saveBtn: {
    backgroundColor: "#5B5BD6",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  savedBtn: { backgroundColor: "#E8E8FF" },
  saveBtnText: { fontSize: 14, fontWeight: "600", color: "#fff" },
  savedBtnText: { color: "#5B5BD6" },
  content: { padding: 16, paddingBottom: 40 },
  hero: { flexDirection: "row", alignItems: "flex-start", marginBottom: 20 },
  avatarLarge: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: "#E0E0FF",
    marginRight: 16,
  },
  heroInfo: { flex: 1, paddingTop: 4 },
  displayName: { fontSize: 22, fontWeight: "700", color: "#1A1A1A", marginBottom: 6 },
  badgeChip: {
    backgroundColor: "#FFF8E7",
    borderColor: "#FFD700",
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 3,
    alignSelf: "flex-start",
    marginBottom: 6,
  },
  badgeText: { fontSize: 12, color: "#B8860B", fontWeight: "600" },
  location: { fontSize: 14, color: "#8A8A8A" },
  section: { marginBottom: 20 },
  sectionLabel: { fontSize: 12, fontWeight: "700", color: "#A0A0A0", textTransform: "uppercase", marginBottom: 8 },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    backgroundColor: "#F0F0FF",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 16,
  },
  chipText: { fontSize: 13, color: "#5B5BD6" },
  metaRow: { flexDirection: "row", gap: 16, marginBottom: 20 },
  metaItem: {
    flex: 1,
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 12,
    borderColor: "#E8E8E8",
    borderWidth: 1,
  },
  metaLabel: { fontSize: 11, color: "#A0A0A0", marginBottom: 4, textTransform: "uppercase" },
  metaValue: { fontSize: 14, fontWeight: "600", color: "#1A1A1A" },
  bioText: { fontSize: 15, color: "#3A3A3A", lineHeight: 22 },
  portfolioItem: { width: 160, marginRight: 12 },
  portfolioThumb: { width: 160, height: 120, borderRadius: 10, backgroundColor: "#E8E8E8", marginBottom: 6 },
  portfolioCaption: { fontSize: 12, color: "#6A6A6A" },
  lastActive: { fontSize: 13, color: "#B0B0B0", marginBottom: 20 },
  hiddenConfirm: { flex: 1, alignItems: "center", justifyContent: "center", padding: 32 },
  hiddenTitle: { fontSize: 20, fontWeight: "700", color: "#1A1A1A", marginBottom: 8 },
  hiddenSubtitle: { fontSize: 15, color: "#6A6A6A", textAlign: "center", lineHeight: 22, marginBottom: 24 },
  backToFeedBtn: { backgroundColor: "#5B5BD6", paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10 },
  backToFeedText: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
