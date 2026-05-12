/**
 * Profile View Screen — own profile + other user profiles.
 *
 * Own profile (isOwnProfile=true):
 *   - Shows health score, badge state + action hints
 *   - Edit button → ProfileSetupWizard
 *
 * Other user profile:
 *   - Public view: city/country only (no lat/lng)
 *   - Portfolio only shows ai_review_status='passed' items
 *   - Valid Profile Badge indicator
 *   - Send Vibe Check CTA
 */

import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

type Props = {
  navigation: NativeStackNavigationProp<any, "ProfileView">;
  route?: { params?: { profileHandle?: string } };
};

interface VocationItem {
  category: string;
  subtag: string;
  is_primary: boolean;
}

interface PortfolioItem {
  id: string;
  type: string;
  caption: string | null;
  ai_review_status: string;
}

interface ProfileData {
  id: string;
  display_name: string | null;
  bio: string | null;
  obsessed_with: string | null;
  location_city: string | null;
  location_country: string | null;
  open_to_remote: boolean;
  experience_level: number | null;
  vocations: VocationItem[];
  personality_archetype: string | null;
  portfolio: PortfolioItem[];
  externals: { provider: string; provider_handle: string | null; sync_state: string }[];
  badge_state: string;
  badge_granted_at: string | null;
  profile_health_score?: number;
  last_active_at: string | null;
}

const BADGE_LABELS: Record<string, { label: string; color: string }> = {
  badge_granted: { label: "Valid Profile", color: "#22c55e" },
  badge_held: { label: "Under Review", color: "#f59e0b" },
  badge_revoked: { label: "Badge Revoked", color: "#ef4444" },
  unverified: { label: "Unverified", color: "#9ca3af" },
  email_verified: { label: "Email Verified", color: "#9ca3af" },
  identity_pending: { label: "Verifying Identity", color: "#60a5fa" },
  identity_approved: { label: "Identity Approved", color: "#60a5fa" },
  ai_review_pending: { label: "Reviewing Profile", color: "#60a5fa" },
};

export function ProfileViewScreen({ navigation, route }: Props): React.ReactElement {
  const profileHandle = route?.params?.profileHandle;
  const isOwnProfile = !profileHandle;

  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProfile();
  }, [profileHandle]);

  const loadProfile = async () => {
    setLoading(true);
    try {
      // TODO: const data = isOwnProfile
      //   ? await profileApi.getOwnProfile()
      //   : await profileApi.getPublicProfile(profileHandle!);
      // setProfile(data);

      // Stub data
      setProfile({
        id: "stub-id",
        display_name: profileHandle || "yourusername",
        bio: "Making music and finding collaborators who care as much as I do.",
        obsessed_with: "the gap between a good idea and a great one",
        location_city: "Brooklyn",
        location_country: "US",
        open_to_remote: true,
        experience_level: 3,
        vocations: [
          { category: "Music & Audio", subtag: "music-producer", is_primary: true },
          { category: "Performing Arts", subtag: "dancer-hiphop", is_primary: false },
        ],
        personality_archetype: "craftsperson",
        portfolio: [
          { id: "p1", type: "audio", caption: "Unreleased EP excerpt", ai_review_status: "passed" },
          { id: "p2", type: "image", caption: "Studio session", ai_review_status: "passed" },
        ],
        externals: [
          { provider: "spotify", provider_handle: "@artname", sync_state: "ok" },
        ],
        badge_state: "badge_granted",
        badge_granted_at: new Date().toISOString(),
        profile_health_score: isOwnProfile ? 72 : undefined,
        last_active_at: new Date().toISOString(),
      });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <ActivityIndicator style={{ flex: 1 }} />;
  if (error || !profile) return (
    <View style={styles.center}>
      <Text style={styles.errorText}>{error || "Profile not found."}</Text>
    </View>
  );

  const badge = BADGE_LABELS[profile.badge_state] || { label: profile.badge_state, color: "#9ca3af" };
  const primaryVocation = profile.vocations.find((v) => v.is_primary);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.avatarPlaceholder}>
          <Text style={styles.avatarText}>
            {(profile.display_name || "?")[0].toUpperCase()}
          </Text>
        </View>
        <View style={styles.headerInfo}>
          <Text style={styles.displayName}>{profile.display_name || "No name yet"}</Text>
          {primaryVocation && (
            <Text style={styles.primaryVocation}>{primaryVocation.subtag}</Text>
          )}
          <View style={[styles.badgePill, { backgroundColor: badge.color + "22", borderColor: badge.color }]}>
            <View style={[styles.badgeDot, { backgroundColor: badge.color }]} />
            <Text style={[styles.badgeLabel, { color: badge.color }]}>{badge.label}</Text>
          </View>
        </View>
        {isOwnProfile && (
          <TouchableOpacity
            onPress={() => navigation.navigate("ProfileSetupWizard" as never)}
            style={styles.editBtn}
          >
            <Text style={styles.editBtnText}>Edit</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Health score (own profile only) */}
      {isOwnProfile && profile.profile_health_score !== undefined && (
        <View style={styles.healthRow}>
          <Text style={styles.healthLabel}>Profile Health</Text>
          <View style={styles.healthBar}>
            <View style={[styles.healthFill, { width: `${profile.profile_health_score}%` }]} />
          </View>
          <Text style={styles.healthScore}>{Math.round(profile.profile_health_score)}%</Text>
        </View>
      )}

      {/* Location */}
      {profile.location_city && (
        <Text style={styles.location}>
          {profile.location_city}, {profile.location_country}
          {profile.open_to_remote ? " · Open to remote" : ""}
        </Text>
      )}

      {/* Bio */}
      {profile.bio && <Text style={styles.bio}>{profile.bio}</Text>}

      {/* Obsessed with */}
      {profile.obsessed_with && (
        <View style={styles.obsessedBlock}>
          <Text style={styles.obsessedLabel}>Obsessed with</Text>
          <Text style={styles.obsessedText}>{profile.obsessed_with}</Text>
        </View>
      )}

      {/* Personality archetype */}
      {profile.personality_archetype && (
        <Text style={styles.archetype}>
          {profile.personality_archetype.charAt(0).toUpperCase() + profile.personality_archetype.slice(1)}
        </Text>
      )}

      {/* Vocations */}
      <View style={styles.vocationsRow}>
        {profile.vocations.map((v) => (
          <View key={`${v.category}/${v.subtag}`} style={[styles.vocChip, v.is_primary && styles.vocChipPrimary]}>
            <Text style={[styles.vocChipText, v.is_primary && styles.vocChipTextPrimary]}>
              {v.is_primary ? "★ " : ""}{v.subtag}
            </Text>
          </View>
        ))}
      </View>

      {/* Portfolio */}
      <Text style={styles.sectionLabel}>Portfolio</Text>
      {profile.portfolio.length === 0 ? (
        <Text style={styles.emptySection}>No portfolio items yet.</Text>
      ) : (
        <View style={styles.portfolioGrid}>
          {profile.portfolio.map((item) => (
            <View key={item.id} style={styles.portfolioCard}>
              <Text style={styles.portfolioType}>{item.type.toUpperCase()}</Text>
              <Text style={styles.portfolioCaption} numberOfLines={2}>
                {item.caption || "Untitled"}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Externals */}
      {profile.externals.length > 0 && (
        <>
          <Text style={styles.sectionLabel}>Social links</Text>
          {profile.externals.map((ext) => (
            <Text key={ext.provider} style={styles.externalRow}>
              {ext.provider}: {ext.provider_handle || "–"}
            </Text>
          ))}
        </>
      )}

      {/* Send Vibe Check CTA (other profiles only) */}
      {!isOwnProfile && (
        <TouchableOpacity style={styles.vibeCheckBtn}>
          <Text style={styles.vibeCheckBtnText}>Send Vibe Check</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  content: { padding: 24, paddingBottom: 48 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  errorText: { color: "red" },
  header: { flexDirection: "row", alignItems: "flex-start", marginBottom: 16 },
  avatarPlaceholder: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: "#000",
    alignItems: "center", justifyContent: "center", marginRight: 16,
  },
  avatarText: { color: "#fff", fontSize: 28, fontWeight: "700" },
  headerInfo: { flex: 1 },
  displayName: { fontSize: 22, fontWeight: "700", marginBottom: 4 },
  primaryVocation: { fontSize: 14, color: "#666", marginBottom: 8 },
  badgePill: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: 12, borderWidth: 1, alignSelf: "flex-start",
  },
  badgeDot: { width: 6, height: 6, borderRadius: 3, marginRight: 6 },
  badgeLabel: { fontSize: 12, fontWeight: "600" },
  editBtn: { padding: 8 },
  editBtnText: { fontSize: 14, color: "#000", fontWeight: "600" },
  healthRow: { flexDirection: "row", alignItems: "center", marginBottom: 12, gap: 8 },
  healthLabel: { fontSize: 12, color: "#666", width: 90 },
  healthBar: { flex: 1, height: 6, backgroundColor: "#eee", borderRadius: 3 },
  healthFill: { height: 6, backgroundColor: "#000", borderRadius: 3 },
  healthScore: { fontSize: 12, fontWeight: "700", width: 36, textAlign: "right" },
  location: { fontSize: 14, color: "#666", marginBottom: 12 },
  bio: { fontSize: 15, lineHeight: 22, marginBottom: 16 },
  obsessedBlock: { backgroundColor: "#f9f9f9", borderRadius: 10, padding: 14, marginBottom: 16 },
  obsessedLabel: { fontSize: 11, fontWeight: "700", color: "#999", marginBottom: 4 },
  obsessedText: { fontSize: 15, fontStyle: "italic" },
  archetype: { fontSize: 13, color: "#999", marginBottom: 12, fontWeight: "600" },
  vocationsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 20 },
  vocChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16,
    backgroundColor: "#f0f0f0",
  },
  vocChipPrimary: { backgroundColor: "#000" },
  vocChipText: { fontSize: 13, color: "#333" },
  vocChipTextPrimary: { color: "#fff" },
  sectionLabel: { fontSize: 14, fontWeight: "700", marginBottom: 12 },
  emptySection: { color: "#999", fontSize: 13, marginBottom: 16 },
  portfolioGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 20 },
  portfolioCard: {
    width: "47%", borderRadius: 10, backgroundColor: "#f5f5f5", padding: 16, aspectRatio: 1,
  },
  portfolioType: { fontSize: 10, fontWeight: "700", color: "#999", marginBottom: 8 },
  portfolioCaption: { fontSize: 13, color: "#333" },
  externalRow: { fontSize: 14, color: "#333", marginBottom: 6 },
  vibeCheckBtn: {
    backgroundColor: "#000", borderRadius: 12, padding: 16,
    alignItems: "center", marginTop: 24,
  },
  vibeCheckBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
