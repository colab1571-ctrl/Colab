/**
 * SavedListScreen — private list of saved profiles (most-recent-first).
 *
 * Spec FR-B-9: User can view their saved profiles.
 * Data source: GET /me/saved → ordered by saved_at DESC.
 * Saved count on each profile is anonymized (spec).
 * Premium-Pro users see who saved them (separate view, not this list).
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

import { getSavedProfiles, unsaveProfile, type ProfileCard } from "../../api/discovery";

interface Props {
  onSelectProfile: (p: ProfileCard) => void;
}

export function SavedListScreen({ onSelectProfile }: Props): React.ReactElement {
  const [profiles, setProfiles] = useState<ProfileCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getSavedProfiles();
      setProfiles(resp.profiles);
    } catch {
      setError("Could not load saved profiles.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleUnsave = async (profileId: string) => {
    try {
      await unsaveProfile(profileId);
      setProfiles((prev) => prev.filter((p) => p.id !== profileId));
    } catch {
      // Non-fatal; show no error
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color="#5B5BD6" size="large" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={load}>
          <Text style={styles.retryText}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (profiles.length === 0) {
    return (
      <View style={styles.centered}>
        <Text style={styles.emptyTitle}>No saved profiles</Text>
        <Text style={styles.emptySubtitle}>Save profiles from your feed to find them here.</Text>
      </View>
    );
  }

  return (
    <FlatList
      data={profiles}
      keyExtractor={(p) => p.id}
      contentContainerStyle={styles.list}
      renderItem={({ item }) => (
        <View style={styles.row}>
          <TouchableOpacity style={styles.rowContent} onPress={() => onSelectProfile(item)}>
            <View style={styles.avatar} />
            <View style={styles.info}>
              <Text style={styles.displayName}>{item.display_name}</Text>
              {item.location_city && (
                <Text style={styles.location}>{item.location_city}</Text>
              )}
              {item.vocations.length > 0 && (
                <Text style={styles.vocation}>{item.vocations[0].subtag}</Text>
              )}
            </View>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.unsaveBtn}
            onPress={() => handleUnsave(item.id)}
          >
            <Text style={styles.unsaveBtnText}>Unsave</Text>
          </TouchableOpacity>
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  errorText: { fontSize: 15, color: "#D32F2F", marginBottom: 12 },
  retryBtn: { backgroundColor: "#5B5BD6", paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 },
  retryText: { color: "#fff", fontWeight: "600" },
  emptyTitle: { fontSize: 18, fontWeight: "700", color: "#1A1A1A", marginBottom: 8 },
  emptySubtitle: { fontSize: 14, color: "#8A8A8A", textAlign: "center" },
  list: { padding: 12 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  rowContent: { flex: 1, flexDirection: "row", alignItems: "center" },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#E0E0FF", marginRight: 12 },
  info: { flex: 1 },
  displayName: { fontSize: 15, fontWeight: "700", color: "#1A1A1A" },
  location: { fontSize: 13, color: "#8A8A8A", marginTop: 2 },
  vocation: { fontSize: 13, color: "#5B5BD6", marginTop: 2 },
  unsaveBtn: {
    backgroundColor: "#F5F5F5",
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
  },
  unsaveBtnText: { fontSize: 13, color: "#6A6A6A" },
});
