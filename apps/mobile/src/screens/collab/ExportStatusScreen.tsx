import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  Text,
  View,
} from "react-native";
import { useRoute } from "@react-navigation/native";

interface ExportStatus {
  export_id: string;
  collab_id: string;
  status: "pending" | "generating" | "ready" | "failed";
  pdf_url: string | null;
  zip_url: string | null;
  expires_at: string | null;
  requested_at: string;
  completed_at: string | null;
}

const POLL_INTERVAL_MS = 5000; // Poll every 5 seconds
const MAX_POLLS = 72; // 72 × 5s = 6 minutes (beyond P95 threshold)

function useExportStatus(exportId: string) {
  const [status, setStatus] = useState<ExportStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollCount = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const resp = await fetch(`/collabs/exports/${exportId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: ExportStatus = await resp.json();
      setStatus(data);
      setError(null);

      if (data.status === "ready" || data.status === "failed") {
        // Stop polling
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
      pollCount.current += 1;
      if (pollCount.current >= MAX_POLLS && timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
        setError("Export is taking longer than expected. Please try again later.");
      }
    }
  }, [exportId]);

  useEffect(() => {
    poll(); // Immediate first poll
    timerRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [poll]);

  return { status, loading, error };
}

function statusMessage(status: string): string {
  switch (status) {
    case "pending":
      return "Export queued...";
    case "generating":
      return "Generating PDF and media archive...";
    case "ready":
      return "Export ready!";
    case "failed":
      return "Export failed.";
    default:
      return status;
  }
}

export function ExportStatusScreen(): React.ReactElement {
  const route = useRoute<any>();
  const { exportId } = route.params as { exportId: string };
  const { status, loading, error } = useExportStatus(exportId);

  const handleDownload = useCallback(async (url: string) => {
    try {
      const supported = await Linking.canOpenURL(url);
      if (supported) {
        await Linking.openURL(url);
      } else {
        Alert.alert("Error", "Cannot open download URL.");
      }
    } catch (e) {
      Alert.alert("Error", (e as Error).message);
    }
  }, []);

  if (loading && !status) {
    return (
      <View className="flex-1 bg-white items-center justify-center">
        <ActivityIndicator size="large" color="#4f46e5" />
        <Text className="text-neutral-400 mt-4">Checking export status...</Text>
      </View>
    );
  }

  if (error && !status) {
    return (
      <View className="flex-1 bg-white items-center justify-center px-6">
        <Text className="text-red-500 text-center">{error}</Text>
      </View>
    );
  }

  const isReady = status?.status === "ready";
  const isFailed = status?.status === "failed";
  const isPending = status?.status === "pending" || status?.status === "generating";

  return (
    <View className="flex-1 bg-neutral-50 px-4 pt-12">
      {/* Status indicator */}
      <View className="bg-white rounded-2xl shadow-sm p-6 items-center">
        {isPending && (
          <>
            <ActivityIndicator size="large" color="#4f46e5" />
            <Text className="text-neutral-700 font-semibold mt-4 text-base">
              {statusMessage(status?.status ?? "pending")}
            </Text>
            <Text className="text-neutral-400 text-sm mt-2 text-center">
              Typical exports complete in under 60 seconds.{"\n"}
              You can leave this screen and come back.
            </Text>
          </>
        )}

        {isReady && (
          <>
            <Text className="text-4xl">✓</Text>
            <Text className="text-neutral-900 font-bold text-xl mt-3">
              Export Ready
            </Text>
            {status?.expires_at && (
              <Text className="text-neutral-400 text-sm mt-1">
                Available until{" "}
                {new Date(status.expires_at).toLocaleDateString()}
              </Text>
            )}

            {/* Download buttons */}
            <View className="w-full mt-6 gap-3">
              {status?.pdf_url && (
                <Pressable
                  onPress={() => handleDownload(status.pdf_url!)}
                  className="bg-indigo-600 py-3 rounded-xl items-center"
                >
                  <Text className="text-white font-semibold">
                    Download PDF Transcript
                  </Text>
                </Pressable>
              )}
              {status?.zip_url && (
                <Pressable
                  onPress={() => handleDownload(status.zip_url!)}
                  className="border border-indigo-400 py-3 rounded-xl items-center"
                >
                  <Text className="text-indigo-600 font-semibold">
                    Download Media Archive (ZIP)
                  </Text>
                </Pressable>
              )}
              {!status?.zip_url && isReady && (
                <Text className="text-neutral-400 text-sm text-center">
                  No media attachments in this collaboration.
                </Text>
              )}
            </View>
          </>
        )}

        {isFailed && (
          <>
            <Text className="text-4xl">✗</Text>
            <Text className="text-red-600 font-bold text-xl mt-3">
              Export Failed
            </Text>
            <Text className="text-neutral-400 text-sm mt-2 text-center">
              Something went wrong generating your export.{"\n"}
              Please try requesting a new export.
            </Text>
          </>
        )}
      </View>

      {/* Metadata */}
      {status && (
        <View className="bg-white rounded-2xl shadow-sm p-4 mt-4">
          <Text className="text-xs text-neutral-400">
            Export ID: {status.export_id}
          </Text>
          <Text className="text-xs text-neutral-400 mt-1">
            Requested: {new Date(status.requested_at).toLocaleString()}
          </Text>
          {status.completed_at && (
            <Text className="text-xs text-neutral-400 mt-1">
              Completed: {new Date(status.completed_at).toLocaleString()}
            </Text>
          )}
        </View>
      )}
    </View>
  );
}
