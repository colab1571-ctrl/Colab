/**
 * FeedScreen — home feed with scroll/swipe mode toggle.
 *
 * Spec FR-B-1, FR-B-2, FR-B-3, FR-B-4:
 * - Infinite scroll list mode OR swipeable card stack mode
 * - User preference persisted via POST /feed/preference/mode
 * - Daily cap enforcement: free users see cap banner at 30 profiles/day
 * - Filters via FiltersDrawer
 *
 * Mode preference is persisted server-side AND in AsyncStorage for instant
 * cold-start rendering without a network round-trip.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { getFeed, setFeedMode, type FeedFilters, type FeedMode, type ProfileCard } from "../../api/discovery";
import { FiltersDrawer } from "./FiltersDrawer";
import { ProfileDetailScreen } from "./ProfileDetailScreen";
import { PickedForYouTab } from "./PickedForYouTab";

const FEED_MODE_KEY = "colab:feed_mode";

// ---------------------------------------------------------------------------
// Profile card (scroll mode)
// ---------------------------------------------------------------------------

function ProfileCardItem({
  profile,
  onPress,
}: {
  profile: ProfileCard;
  onPress: (p: ProfileCard) => void;
}): React.ReactElement {
  return (
    <TouchableOpacity
      style={styles.card}
      onPress={() => onPress(profile)}
      activeOpacity={0.85}
    >
      <View style={styles.cardHeader}>
        <View style={styles.avatar} />
        <View style={styles.cardInfo}>
          <Text style={styles.displayName}>{profile.display_name}</Text>
          {profile.location_city && (
            <Text style={styles.location}>{profile.location_city}</Text>
          )}
        </View>
      </View>
      {profile.vocations.length > 0 && (
        <View style={styles.vocationsRow}>
          {profile.vocations.map((v, i) => (
            <View key={i} style={styles.vocationChip}>
              <Text style={styles.vocationText}>{v.subtag}</Text>
            </View>
          ))}
        </View>
      )}
      {profile.bio && (
        <Text style={styles.bio} numberOfLines={2}>
          {profile.bio}
        </Text>
      )}
      <Text style={styles.lastActive}>{profile.last_active_relative}</Text>
    </TouchableOpacity>
  );
}

// ---------------------------------------------------------------------------
// Swipe card stack (swipe mode — simplified stack)
// ---------------------------------------------------------------------------

function SwipeCardStack({
  profiles,
  onHide,
  onSave,
  onViewDetail,
}: {
  profiles: ProfileCard[];
  onHide: (p: ProfileCard) => void;
  onSave: (p: ProfileCard) => void;
  onViewDetail: (p: ProfileCard) => void;
}): React.ReactElement {
  const [index, setIndex] = useState(0);
  const current = profiles[index];

  if (!current) {
    return (
      <View style={styles.emptyStack}>
        <Text style={styles.emptyText}>No more profiles right now.</Text>
      </View>
    );
  }

  return (
    <View style={styles.swipeContainer}>
      <TouchableOpacity
        style={styles.swipeCard}
        onPress={() => onViewDetail(current)}
        activeOpacity={0.9}
      >
        <Text style={styles.swipeDisplayName}>{current.display_name}</Text>
        {current.location_city && (
          <Text style={styles.swipeLocation}>{current.location_city}</Text>
        )}
        {current.bio && (
          <Text style={styles.swipeBio} numberOfLines={4}>
            {current.bio}
          </Text>
        )}
      </TouchableOpacity>
      <View style={styles.swipeActions}>
        <TouchableOpacity
          style={[styles.swipeBtn, styles.hideBtnStyle]}
          onPress={() => {
            onHide(current);
            setIndex((i) => i + 1);
          }}
        >
          <Text style={styles.swipeBtnText}>Hide 3mo</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.swipeBtn, styles.saveBtnStyle]}
          onPress={() => {
            onSave(current);
            setIndex((i) => i + 1);
          }}
        >
          <Text style={styles.swipeBtnText}>Save</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.swipeBtn, styles.passBtn]}
          onPress={() => setIndex((i) => i + 1)}
        >
          <Text style={styles.swipeBtnText}>Pass</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// FeedScreen
// ---------------------------------------------------------------------------

export function FeedScreen(): React.ReactElement {
  const [mode, setMode] = useState<FeedMode>("scroll");
  const [profiles, setProfiles] = useState<ProfileCard[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [filters, setFilters] = useState<FeedFilters>({});
  const [loading, setLoading] = useState(false);
  const [capReached, setCapReached] = useState(false);
  const [capResetAt, setCapResetAt] = useState<string | null>(null);
  const [remainingToday, setRemainingToday] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<ProfileCard | null>(null);
  const [showPickedTab, setShowPickedTab] = useState(false);

  // Load persisted mode on mount
  useEffect(() => {
    AsyncStorage.getItem(FEED_MODE_KEY).then((saved) => {
      if (saved === "scroll" || saved === "swipe") setMode(saved);
    });
  }, []);

  const loadMore = useCallback(async () => {
    if (loading || capReached) return;
    setLoading(true);
    try {
      const resp = await getFeed({ mode, cursor, filters, pageSize: 20 });
      setProfiles((prev) => (cursor ? [...prev, ...resp.profiles] : resp.profiles));
      setCursor(resp.next_cursor);
      if (resp.remaining_today !== undefined) {
        setRemainingToday(resp.remaining_today);
      }
      if (!resp.next_cursor && resp.remaining_today === 0) {
        setCapReached(true);
      }
    } catch (err: unknown) {
      const e = err as { status?: number; body?: { resets_at?: string } };
      if (e?.status === 402) {
        setCapReached(true);
        setCapResetAt(e?.body?.resets_at ?? null);
      }
    } finally {
      setLoading(false);
    }
  }, [mode, cursor, filters, loading, capReached]);

  // Reload when filters or mode change
  useEffect(() => {
    setProfiles([]);
    setCursor(null);
    setCapReached(false);
    loadMore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, filters]);

  const toggleMode = async () => {
    const next: FeedMode = mode === "scroll" ? "swipe" : "scroll";
    setMode(next);
    await AsyncStorage.setItem(FEED_MODE_KEY, next);
    try {
      await setFeedMode(next);
    } catch {
      // Non-fatal; local preference already saved
    }
  };

  if (selectedProfile) {
    return (
      <ProfileDetailScreen
        profile={selectedProfile}
        onBack={() => setSelectedProfile(null)}
      />
    );
  }

  if (showPickedTab) {
    return <PickedForYouTab onBack={() => setShowPickedTab(false)} />;
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Discover</Text>
        <View style={styles.headerActions}>
          <TouchableOpacity style={styles.headerBtn} onPress={() => setShowPickedTab(true)}>
            <Text style={styles.headerBtnText}>Picked ✦</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.headerBtn} onPress={() => setShowFilters(true)}>
            <Text style={styles.headerBtnText}>Filters</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.headerBtn} onPress={toggleMode}>
            <Text style={styles.headerBtnText}>{mode === "scroll" ? "⊡ Swipe" : "☰ Scroll"}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Cap banner */}
      {capReached && (
        <View style={styles.capBanner}>
          <Text style={styles.capText}>
            Daily limit reached (30/day on Free).
            {capResetAt ? ` Resets ${new Date(capResetAt).toLocaleTimeString()}` : ""}
          </Text>
        </View>
      )}

      {/* Remaining counter (free users) */}
      {remainingToday !== null && !capReached && (
        <View style={styles.remainingBar}>
          <Text style={styles.remainingText}>{remainingToday} profiles remaining today</Text>
        </View>
      )}

      {/* Feed content */}
      {mode === "scroll" ? (
        <FlatList
          data={profiles}
          keyExtractor={(p) => p.id}
          renderItem={({ item }) => (
            <ProfileCardItem profile={item} onPress={setSelectedProfile} />
          )}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          ListFooterComponent={loading ? <ActivityIndicator style={{ margin: 16 }} color="#5B5BD6" /> : null}
          contentContainerStyle={styles.list}
        />
      ) : (
        <SwipeCardStack
          profiles={profiles}
          onHide={(p) => console.log("hide", p.id)}
          onSave={(p) => console.log("save", p.id)}
          onViewDetail={setSelectedProfile}
        />
      )}

      {/* Filters drawer */}
      <FiltersDrawer
        visible={showFilters}
        filters={filters}
        onApply={(f) => {
          setFilters(f);
          setShowFilters(false);
        }}
        onClose={() => setShowFilters(false)}
      />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FAFAFA" },
  header: {
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
  title: { fontSize: 22, fontWeight: "700", color: "#1A1A1A" },
  headerActions: { flexDirection: "row", gap: 8 },
  headerBtn: {
    backgroundColor: "#F0F0FF",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
  },
  headerBtnText: { fontSize: 13, color: "#5B5BD6", fontWeight: "600" },
  capBanner: {
    backgroundColor: "#FFF3CD",
    borderColor: "#FFD700",
    borderWidth: 1,
    margin: 12,
    padding: 12,
    borderRadius: 8,
  },
  capText: { fontSize: 13, color: "#856404", textAlign: "center" },
  remainingBar: { paddingHorizontal: 16, paddingVertical: 6 },
  remainingText: { fontSize: 12, color: "#A0A0A0", textAlign: "right" },
  list: { paddingHorizontal: 12, paddingVertical: 8 },
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  cardHeader: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#E0E0FF", marginRight: 12 },
  cardInfo: { flex: 1 },
  displayName: { fontSize: 16, fontWeight: "700", color: "#1A1A1A" },
  location: { fontSize: 13, color: "#8A8A8A", marginTop: 2 },
  vocationsRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 8 },
  vocationChip: {
    backgroundColor: "#F0F0FF",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
  },
  vocationText: { fontSize: 12, color: "#5B5BD6" },
  bio: { fontSize: 14, color: "#4A4A4A", lineHeight: 20, marginBottom: 8 },
  lastActive: { fontSize: 12, color: "#B0B0B0" },
  // Swipe
  swipeContainer: { flex: 1, alignItems: "center", justifyContent: "center", padding: 20 },
  swipeCard: {
    width: "100%",
    backgroundColor: "#fff",
    borderRadius: 20,
    padding: 24,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
    marginBottom: 24,
  },
  swipeDisplayName: { fontSize: 24, fontWeight: "700", color: "#1A1A1A", marginBottom: 6 },
  swipeLocation: { fontSize: 15, color: "#8A8A8A", marginBottom: 12 },
  swipeBio: { fontSize: 15, color: "#4A4A4A", lineHeight: 22 },
  swipeActions: { flexDirection: "row", gap: 12 },
  swipeBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: "center",
  },
  hideBtnStyle: { backgroundColor: "#F5F5F5" },
  saveBtnStyle: { backgroundColor: "#5B5BD6" },
  passBtn: { backgroundColor: "#F0F0F0" },
  swipeBtnText: { fontSize: 14, fontWeight: "600", color: "#1A1A1A" },
  emptyStack: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyText: { fontSize: 16, color: "#A0A0A0" },
});
