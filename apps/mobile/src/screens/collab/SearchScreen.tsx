import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";

interface CollabSearchResult {
  id: string;
  title: string | null;
  status: string;
  last_activity_at: string;
  archived_at: string | null;
  partner: { profile_id: string; display_name: string; avatar_url: string | null };
}

const DEBOUNCE_MS = 350;

function useCollabSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CollabSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ q, status: "all", include_archived: "true", limit: "30" });
      const resp = await fetch(`/collabs?${params.toString()}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setResults(data.data ?? []);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleQueryChange = useCallback(
    (text: string) => {
      setQuery(text);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => search(text), DEBOUNCE_MS);
    },
    [search]
  );

  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

  return { query, handleQueryChange, results, loading, error };
}

function statusColor(status: string): string {
  switch (status) {
    case "in_progress": return "#4f46e5";
    case "still_deciding": return "#f59e0b";
    case "completed": return "#16a34a";
    default: return "#9ca3af";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "still_deciding": return "Still Deciding";
    case "in_progress": return "In Progress";
    case "completed": return "Completed";
    case "didnt_work_out": return "Didn't Work Out";
    default: return status;
  }
}

export function SearchScreen(): React.ReactElement {
  const navigation = useNavigation<any>();
  const { query, handleQueryChange, results, loading, error } = useCollabSearch();

  return (
    <View className="flex-1 bg-neutral-50">
      {/* Search bar */}
      <View className="bg-white px-4 pt-4 pb-3 shadow-sm">
        <View className="flex-row items-center bg-neutral-100 rounded-xl px-3 py-2">
          <Text className="text-neutral-400 mr-2 text-base">Search</Text>
          <TextInput
            value={query}
            onChangeText={handleQueryChange}
            placeholder="Titles, descriptions, names, file names..."
            placeholderTextColor="#9ca3af"
            className="flex-1 text-neutral-900 text-base"
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
          />
          {loading && <ActivityIndicator size="small" color="#4f46e5" />}
        </View>
        <Text className="text-xs text-neutral-400 mt-1 ml-1">
          Note: chat message content is not searchable.
        </Text>
      </View>

      {/* Results */}
      {error ? (
        <View className="flex-1 items-center justify-center">
          <Text className="text-red-500">{error}</Text>
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            query.trim().length > 0 && !loading ? (
              <View className="flex-1 items-center justify-center py-16">
                <Text className="text-neutral-400">No results for "{query}"</Text>
              </View>
            ) : !query.trim() ? (
              <View className="flex-1 items-center justify-center py-16">
                <Text className="text-neutral-400 text-base">
                  Search your collaboration history
                </Text>
                <Text className="text-neutral-400 text-sm mt-1">
                  Find by project title, partner name, or file name
                </Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => (
            <Pressable
              onPress={() =>
                navigation.navigate("CollabDetail", { collabId: item.id })
              }
              className="bg-white mx-4 my-2 rounded-2xl shadow-sm overflow-hidden"
            >
              <View className="p-4">
                <View className="flex-row items-center justify-between mb-1">
                  <Text
                    className="text-base font-semibold text-neutral-900 flex-1 mr-2"
                    numberOfLines={1}
                  >
                    {item.title ?? `Collab with ${item.partner.display_name}`}
                  </Text>
                  <View
                    className="px-2 py-1 rounded-full"
                    style={{ backgroundColor: statusColor(item.status) + "20" }}
                  >
                    <Text
                      className="text-xs font-medium"
                      style={{ color: statusColor(item.status) }}
                    >
                      {statusLabel(item.status)}
                    </Text>
                  </View>
                </View>
                <Text className="text-sm text-neutral-500">
                  {item.partner.display_name}
                </Text>
              </View>
            </Pressable>
          )}
          contentContainerStyle={
            results.length === 0 ? { flex: 1 } : { paddingVertical: 8 }
          }
        />
      )}
    </View>
  );
}
