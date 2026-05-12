import React from "react";
import { ActivityIndicator, Text, TouchableOpacity, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useHelloQuery } from "../../api/queries/hello.queries";

export function HomeScreen(): React.ReactElement {
  const { data, isLoading, error, refetch } = useHelloQuery();

  return (
    <View className="flex-1 bg-white items-center justify-center px-6">
      <Text className="text-3xl font-bold text-brand-primary mb-2">Colab</Text>
      <Text className="text-base text-neutral-500 mb-8">Shared Platform — P1</Text>

      {isLoading && <ActivityIndicator color="#5B5BD6" />}

      {data && (
        <View className="bg-neutral-50 border border-neutral-200 rounded-xl p-4 w-full mb-6">
          <Text className="text-sm font-semibold text-neutral-700 mb-1">Gateway Response</Text>
          <Text className="text-sm text-neutral-500">Message: {data.msg}</Text>
          <Text className="text-sm text-neutral-500">Env: {data.env}</Text>
          <Text className="text-sm text-neutral-400 mt-1" numberOfLines={1}>
            req_id: {data.request_id}
          </Text>
        </View>
      )}

      {error && (
        <Text className="text-sm text-error text-center mb-4">
          Could not reach gateway. Is it running?
        </Text>
      )}

      <TouchableOpacity
        className="bg-brand-primary px-8 py-3 rounded-xl"
        onPress={() => void refetch()}
      >
        <Text className="text-white font-semibold">Ping Gateway</Text>
      </TouchableOpacity>
    </View>
  );
}
