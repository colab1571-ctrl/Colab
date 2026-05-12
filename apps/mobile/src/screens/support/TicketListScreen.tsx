/**
 * TicketListScreen — View all of the user's support tickets.
 *
 * GET /v1/support/tickets?status=<filter>&page=<n>
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useAuthStore } from "../../state/auth.store";

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In Progress",
  pending_user: "Waiting for You",
  resolved: "Resolved",
  closed: "Closed",
};

const STATUS_COLORS: Record<string, string> = {
  open: "text-blue-600 bg-blue-50",
  in_progress: "text-yellow-700 bg-yellow-50",
  pending_user: "text-orange-600 bg-orange-50",
  resolved: "text-green-700 bg-green-50",
  closed: "text-neutral-500 bg-neutral-100",
};

interface Ticket {
  id: string;
  category: string;
  subject: string;
  status: string;
  priority: string;
  sla_ack_due: string;
  created_at: string;
}

interface Props {
  navigation: {
    navigate: (screen: string, params?: Record<string, unknown>) => void;
  };
}

const FILTERS = ["all", "open", "in_progress", "resolved"] as const;

export function TicketListScreen({ navigation }: Props): React.ReactElement {
  const { access_token } = useAuthStore();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const fetchTickets = useCallback(
    async (pageNum: number, status: string) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ page: String(pageNum), per_page: "20" });
        if (status !== "all") params.set("status", status);

        const resp = await fetch(`${BASE_URL}/v1/support/tickets?${params.toString()}`, {
          headers: { Authorization: `Bearer ${access_token}` },
        });
        if (!resp.ok) throw new Error("Failed to load tickets");
        const data = await resp.json();
        setTickets(pageNum === 1 ? data.tickets : (prev) => [...prev, ...data.tickets]);
        setTotal(data.total);
      } catch {
        setError("Unable to load tickets. Please try again.");
      } finally {
        setLoading(false);
      }
    },
    [access_token]
  );

  useEffect(() => {
    setPage(1);
    fetchTickets(1, statusFilter);
  }, [statusFilter, fetchTickets]);

  const loadMore = () => {
    if (tickets.length < total && !loading) {
      const nextPage = page + 1;
      setPage(nextPage);
      fetchTickets(nextPage, statusFilter);
    }
  };

  const renderTicket = ({ item }: { item: Ticket }) => (
    <TouchableOpacity
      className="px-4 py-3 border-b border-neutral-100"
      onPress={() => navigation.navigate("TicketDetail", { ticketId: item.id })}
      accessibilityRole="button"
      accessibilityLabel={`Ticket: ${item.subject}`}
    >
      <View className="flex-row items-start justify-between">
        <Text
          className="flex-1 text-sm font-medium text-neutral-900 mr-2"
          numberOfLines={2}
        >
          {item.subject}
        </Text>
        <View className={`rounded-full px-2 py-0.5 ${STATUS_COLORS[item.status] ?? "bg-neutral-100"}`}>
          <Text className={`text-xs font-medium ${STATUS_COLORS[item.status]?.split(" ")[0] ?? "text-neutral-600"}`}>
            {STATUS_LABELS[item.status] ?? item.status}
          </Text>
        </View>
      </View>
      <Text className="text-xs text-neutral-400 mt-1 capitalize">
        {item.category.replace(/_/g, " ")}
      </Text>
    </TouchableOpacity>
  );

  return (
    <View className="flex-1 bg-white">
      {/* Status filter tabs */}
      <View className="flex-row border-b border-neutral-200 px-2">
        {FILTERS.map((f) => (
          <TouchableOpacity
            key={f}
            className={`px-3 py-3 ${statusFilter === f ? "border-b-2 border-blue-600" : ""}`}
            onPress={() => setStatusFilter(f)}
            accessibilityRole="tab"
            accessibilityState={{ selected: statusFilter === f }}
          >
            <Text
              className={`text-sm capitalize ${
                statusFilter === f ? "text-blue-600 font-medium" : "text-neutral-500"
              }`}
            >
              {f === "all" ? "All" : f.replace(/_/g, " ")}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading && tickets.length === 0 ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator size="large" color="#2563EB" />
        </View>
      ) : error ? (
        <View className="flex-1 items-center justify-center px-6">
          <Text className="text-neutral-500 text-center mb-4">{error}</Text>
          <TouchableOpacity
            className="bg-blue-600 rounded-lg px-6 py-2"
            onPress={() => fetchTickets(1, statusFilter)}
          >
            <Text className="text-white font-medium">Retry</Text>
          </TouchableOpacity>
        </View>
      ) : tickets.length === 0 ? (
        <View className="flex-1 items-center justify-center px-6">
          <Text className="text-neutral-400 text-center mb-4">No tickets found.</Text>
          <TouchableOpacity
            className="bg-blue-600 rounded-lg px-6 py-2"
            onPress={() => navigation.navigate("SupportTicketForm")}
            accessibilityRole="button"
          >
            <Text className="text-white font-medium">Open a Ticket</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={tickets}
          keyExtractor={(item) => item.id}
          renderItem={renderTicket}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            loading ? <ActivityIndicator className="py-4" color="#2563EB" /> : null
          }
        />
      )}

      {/* FAB — new ticket */}
      <TouchableOpacity
        className="absolute bottom-6 right-6 bg-blue-600 w-14 h-14 rounded-full items-center justify-center shadow-lg"
        onPress={() => navigation.navigate("SupportTicketForm")}
        accessibilityRole="button"
        accessibilityLabel="Open new ticket"
      >
        <Text className="text-white text-2xl leading-none">+</Text>
      </TouchableOpacity>
    </View>
  );
}
