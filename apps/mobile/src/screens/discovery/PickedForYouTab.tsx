/**
 * PickedForYouTab — "AI Recommended Profiles" dedicated tab.
 *
 * Spec FR-B-10:
 * - Shows 5–10 daily recommendations from GET /feed/picked-for-you
 * - Refreshed nightly (03:00 UTC); shows next_refresh_at countdown
 * - Premium users get 10 profiles, Free users get 5
 * - Profiles are cross-discipline first, local second, then top-scoring
 * - Hidden/blocked profiles excluded server-side
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { getPickedForYou, type ProfileCard } from "../../api/discovery";

interface Props {
  onBack: () => void;
}

function timeUntil(isoDate: string): string {
  const diff = new Date(isoDate).getTime() - Date.now();
  if (diff <= 0) return "refreshing…";
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function PickedForYouTab({ onBack }: Props): React.ReactElement {
  const [profiles, setProfiles] = useState<ProfileCard[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [nextRefreshAt, setNextRefreshAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getPickedForYou();
      setProfiles(resp.profiles);
      setGeneratedAt(resp.generated_at);
      setNextRefreshAt(resp.next_refresh_at);
    } catch {
      setError("Could not load recommendations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={onBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Picked for You ✦</Text>
        <View style={{ width: 60 }} />
      </View>

      {/* Refresh indicator */}
      {nextRefreshAt && (
        <View style={styles.refreshBanner}>
          <Text style={styles.refreshText}>
            Refreshes in {timeUntil(nextRefreshAt)}
          </Text>
        </View>
      )}

      {loading && (
        <View style={styles.centered}>
          <ActivityIndicator color="#5B5BD6" size="large" />
          <Text style={styles.loadingText}>Finding your best matches…</Text>
        </View>
      )}

      {error && !loading && (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={load}>
            <Text style={styles.retryText}>Try again</Text>
          </TouchableOpacity>
        </View>
      )}

      {!loading && !error && profiles.length === 0 && (
        <View style={styles.centered}>
          <Text style={styles.emptyTitle}>No picks yet</Text>
          <Text style={styles.emptySubtitle}>
            Complete your profile to get personalized recommendations.
          </Text>
        </View>
      )}

      {!loading && !error && profiles.length > 0 && (
        <>
          <FlatList
            data={profiles}
            keyExtractor={(p) => p.id}
            contentContainerStyle={styles.list}
            renderItem={({ item, index }) => (
              <View style={styles.card}>
                <View style={styles.rankBadge}>
                  <Text style={styles.rankText}>#{index + 1}</Text>
                </View>
                <View style={styles.cardContent}>
                  <View style={styles.avatar} />
                  <View style={styles.info}>
                    <Text style={styles.displayName}>{item.display_name}</Text>
                    {item.location_city && (
                      <Text style={styles.location}>{item.location_city}</Text>
                    )}
                    {item.vocations.length > 0 && (
                      <Text style={styles.vocation}>
                        {item.vocations.map((v) => v.subtag).join(" · ")}
                      </Text>
                    )}
                  </View>
                </View>
                {item.bio && (
                  <Text style={styles.bio} numberOfLines={2}>
                    {item.bio}
                  </Text>
                )}
                <Text style={styles.lastActive}>{item.last_active_relative}</Text>
              </View>
            )}
          />
          {generatedAt && (
            <Text style={styles.generatedAt}>
              Generated {new Date(generatedAt).toLocaleTimeString()}
            </Text>
          )}
        </>
      )}
    </View>
  );
}

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
  backBtn: { width: 60 },
  backText: { fontSize: 16, color: "#5B5BD6" },
  title: { fontSize: 18, fontWeight: "700", color: "#1A1A1A" },
  refreshBanner: {
    backgroundColor: "#F0F0FF",
    paddingVertical: 6,
    paddingHorizontal: 16,
    alignItems: "center",
  },
  refreshText: { fontSize: 12, color: "#5B5BD6" },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  loadingText: { marginTop: 12, fontSize: 14, color: "#8A8A8A" },
  errorText: { fontSize: 15, color: "#D32F2F", marginBottom: 12 },
  retryBtn: { backgroundColor: "#5B5BD6", paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 },
  retryText: { color: "#fff", fontWeight: "600" },
  emptyTitle: { fontSize: 18, fontWeight: "700", color: "#1A1A1A", marginBottom: 8 },
  emptySubtitle: { fontSize: 14, color: "#8A8A8A", textAlign: "center", lineHeight: 20 },
  list: { padding: 12, paddingBottom: 32 },
  card: {
    backgroundColor: "#fff",
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    shadowColor: "#5B5BD6",
    shadowOpacity: 0.08,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
    borderLeftColor: "#5B5BD6",
    borderLeftWidth: 3,
  },
  rankBadge: {
    position: "absolute",
    top: 12,
    right: 12,
    backgroundColor: "#F0F0FF",
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  rankText: { fontSize: 11, color: "#5B5BD6", fontWeight: "700" },
  cardContent: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#E0E0FF", marginRight: 12 },
  info: { flex: 1 },
  displayName: { fontSize: 15, fontWeight: "700", color: "#1A1A1A" },
  location: { fontSize: 13, color: "#8A8A8A", marginTop: 2 },
  vocation: { fontSize: 13, color: "#5B5BD6", marginTop: 2 },
  bio: { fontSize: 14, color: "#4A4A4A", lineHeight: 20, marginBottom: 6 },
  lastActive: { fontSize: 12, color: "#B0B0B0" },
  generatedAt: { textAlign: "center", fontSize: 12, color: "#C0C0C0", paddingBottom: 16 },
});
