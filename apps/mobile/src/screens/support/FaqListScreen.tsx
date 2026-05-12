/**
 * FaqListScreen — Browse and search FAQ articles.
 *
 * Fetches from GET /v1/support/faq (public endpoint).
 * Supports tag filter and keyword search.
 * Taps navigate to FaqDetailScreen via slug.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

interface FaqArticle {
  slug: string;
  title: string;
  body_md: string;
  tags: string[];
  updated_at: string;
}

interface Props {
  navigation: {
    navigate: (screen: string, params?: Record<string, unknown>) => void;
  };
}

export function FaqListScreen({ navigation }: Props): React.ReactElement {
  const [articles, setArticles] = useState<FaqArticle[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchArticles = useCallback(async (q: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      const resp = await fetch(`${BASE_URL}/v1/support/faq?${params.toString()}`);
      if (!resp.ok) throw new Error("Failed to load FAQ");
      const data = await resp.json();
      setArticles(data.articles ?? []);
    } catch (err) {
      setError("Unable to load FAQ articles. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchArticles("");
  }, [fetchArticles]);

  const handleSearch = () => fetchArticles(query);

  const renderItem = ({ item }: { item: FaqArticle }) => (
    <TouchableOpacity
      className="px-4 py-3 border-b border-neutral-100"
      onPress={() => navigation.navigate("FaqDetail", { slug: item.slug })}
      accessibilityRole="button"
      accessibilityLabel={item.title}
    >
      <Text className="text-base font-medium text-neutral-900">{item.title}</Text>
      {item.tags.length > 0 && (
        <View className="flex-row flex-wrap mt-1 gap-1">
          {item.tags.map((tag) => (
            <Text
              key={tag}
              className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full"
            >
              {tag}
            </Text>
          ))}
        </View>
      )}
    </TouchableOpacity>
  );

  return (
    <View className="flex-1 bg-white">
      {/* Search bar */}
      <View className="px-4 py-3 border-b border-neutral-200 flex-row gap-2">
        <TextInput
          className="flex-1 bg-neutral-100 rounded-lg px-3 py-2 text-sm text-neutral-900"
          placeholder="Search help articles…"
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={handleSearch}
          returnKeyType="search"
          accessibilityLabel="Search FAQ"
        />
        <TouchableOpacity
          className="bg-blue-600 rounded-lg px-4 py-2 justify-center"
          onPress={handleSearch}
          accessibilityRole="button"
          accessibilityLabel="Search"
        >
          <Text className="text-white text-sm font-medium">Search</Text>
        </TouchableOpacity>
      </View>

      {/* Quick links */}
      <View className="px-4 py-3 flex-row flex-wrap gap-2">
        {["billing", "account", "technical"].map((tag) => (
          <TouchableOpacity
            key={tag}
            className="bg-neutral-100 rounded-full px-3 py-1"
            onPress={() => fetchArticles(tag)}
            accessibilityRole="button"
            accessibilityLabel={`Filter by ${tag}`}
          >
            <Text className="text-sm text-neutral-600 capitalize">{tag}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator size="large" color="#2563EB" />
        </View>
      ) : error ? (
        <View className="flex-1 items-center justify-center px-6">
          <Text className="text-neutral-500 text-center mb-4">{error}</Text>
          <TouchableOpacity
            className="bg-blue-600 rounded-lg px-6 py-2"
            onPress={() => fetchArticles(query)}
          >
            <Text className="text-white font-medium">Retry</Text>
          </TouchableOpacity>
        </View>
      ) : articles.length === 0 ? (
        <View className="flex-1 items-center justify-center px-6">
          <Text className="text-neutral-400 text-center">No articles found.</Text>
          <TouchableOpacity
            className="mt-4"
            onPress={() => navigation.navigate("SupportTicketForm")}
          >
            <Text className="text-blue-600 text-sm">Open a support ticket instead</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={articles}
          keyExtractor={(item) => item.slug}
          renderItem={renderItem}
          ListFooterComponent={() => (
            <View className="px-4 py-6 items-center">
              <Text className="text-neutral-400 text-sm mb-2">
                Can't find what you're looking for?
              </Text>
              <TouchableOpacity
                onPress={() => navigation.navigate("Chatbot")}
                accessibilityRole="button"
              >
                <Text className="text-blue-600 text-sm font-medium">
                  Chat with our support bot
                </Text>
              </TouchableOpacity>
            </View>
          )}
        />
      )}
    </View>
  );
}
