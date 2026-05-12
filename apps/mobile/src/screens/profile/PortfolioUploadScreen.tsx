/**
 * Portfolio Upload — up to 12 items; image 10MB / audio 30MB / video 100MB.
 *
 * Flow:
 *   1. POST /api/v1/profile/me/portfolio/upload-url → presigned POST fields
 *   2. Direct multipart POST to S3
 *   3. POST /api/v1/profile/me/portfolio/{id}/finalize
 *
 * Uses React Native document/media picker. Upload requires connectivity (no offline queue).
 */

import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

type Props = {
  navigation: NativeStackNavigationProp<any, "PortfolioUpload">;
};

interface PortfolioItem {
  id: string;
  type: "image" | "audio" | "video";
  name: string;
  status: "uploading" | "processing" | "passed" | "flagged";
}

const ITEM_LIMIT = 12;
const SIZE_CAPS: Record<string, number> = {
  image: 10 * 1024 * 1024,
  audio: 30 * 1024 * 1024,
  video: 100 * 1024 * 1024,
};

export function PortfolioUploadScreen({ navigation }: Props): React.ReactElement {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [loading, setLoading] = useState(false);

  const handleAddItem = async (type: "image" | "audio" | "video") => {
    if (items.length >= ITEM_LIMIT) {
      Alert.alert("Limit reached", `You can add up to ${ITEM_LIMIT} portfolio items.`);
      return;
    }

    // In production, launch the native document picker here
    // For now: stub the upload flow
    const stubItem: PortfolioItem = {
      id: `stub-${Date.now()}`,
      type,
      name: `${type}_sample.${type === "image" ? "jpg" : type === "audio" ? "mp3" : "mp4"}`,
      status: "uploading",
    };

    setItems((prev) => [...prev, stubItem]);

    try {
      // 1. Request presigned POST URL
      // const { upload, portfolio_item_id } = await profileApi.getUploadUrl({ type, mime, size_bytes });
      // 2. Upload directly to S3
      // await uploadToS3(upload.url, upload.fields, file);
      // 3. Finalize
      // await profileApi.finalizeUpload(portfolio_item_id, { caption: '' });

      // Simulate async processing
      setTimeout(() => {
        setItems((prev) =>
          prev.map((i) => (i.id === stubItem.id ? { ...i, status: "processing" } : i))
        );
        setTimeout(() => {
          setItems((prev) =>
            prev.map((i) => (i.id === stubItem.id ? { ...i, status: "passed" } : i))
          );
        }, 3000);
      }, 1500);
    } catch (err: any) {
      setItems((prev) => prev.filter((i) => i.id !== stubItem.id));
      Alert.alert("Upload failed", err.message || "Please try again.");
    }
  };

  const handleRemoveItem = (id: string) => {
    Alert.alert("Remove item", "Remove this portfolio item?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: () => setItems((prev) => prev.filter((i) => i.id !== id)),
      },
    ]);
  };

  const renderItem = ({ item }: { item: PortfolioItem }) => (
    <View style={styles.itemCard}>
      <Text style={styles.itemType}>{item.type.toUpperCase()}</Text>
      <Text style={styles.itemName} numberOfLines={1}>{item.name}</Text>
      <View style={styles.itemStatus}>
        {item.status === "uploading" || item.status === "processing" ? (
          <ActivityIndicator size="small" />
        ) : (
          <View style={[styles.statusDot, item.status === "passed" ? styles.dotPassed : styles.dotFlagged]} />
        )}
        <Text style={styles.statusText}>{item.status}</Text>
      </View>
      <TouchableOpacity onPress={() => handleRemoveItem(item.id)}>
        <Text style={styles.removeBtn}>✕</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Build your portfolio</Text>
      <Text style={styles.subheading}>
        Up to {ITEM_LIMIT} items. Image ≤10MB, audio ≤30MB, video ≤100MB.
      </Text>

      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        ListEmptyComponent={
          <Text style={styles.empty}>No items yet. Add your first piece below.</Text>
        }
        style={styles.list}
      />

      <View style={styles.addButtons}>
        <TouchableOpacity style={styles.addBtn} onPress={() => handleAddItem("image")}>
          <Text style={styles.addBtnText}>+ Image</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.addBtn} onPress={() => handleAddItem("audio")}>
          <Text style={styles.addBtnText}>+ Audio</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.addBtn} onPress={() => handleAddItem("video")}>
          <Text style={styles.addBtnText}>+ Video</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.itemCount}>{items.length}/{ITEM_LIMIT} items</Text>

      <TouchableOpacity
        style={[styles.nextBtn, items.length === 0 && styles.nextBtnDisabled]}
        onPress={() => navigation.navigate("PersonalityQuiz" as never)}
      >
        <Text style={styles.nextBtnText}>
          {items.length === 0 ? "Skip for now" : "Continue"}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", padding: 24 },
  heading: { fontSize: 24, fontWeight: "700", marginBottom: 8 },
  subheading: { fontSize: 14, color: "#666", marginBottom: 16 },
  list: { flex: 1, marginBottom: 16 },
  empty: { textAlign: "center", color: "#999", marginTop: 40, fontSize: 14 },
  itemCard: {
    flexDirection: "row", alignItems: "center", padding: 12,
    borderWidth: 1, borderColor: "#eee", borderRadius: 8, marginBottom: 8,
  },
  itemType: { fontSize: 10, fontWeight: "700", color: "#999", width: 40 },
  itemName: { flex: 1, fontSize: 14, marginHorizontal: 8 },
  itemStatus: { flexDirection: "row", alignItems: "center", gap: 6 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  dotPassed: { backgroundColor: "#22c55e" },
  dotFlagged: { backgroundColor: "#ef4444" },
  statusText: { fontSize: 12, color: "#666" },
  removeBtn: { fontSize: 16, color: "#999", paddingLeft: 12 },
  addButtons: { flexDirection: "row", gap: 8, marginBottom: 12 },
  addBtn: {
    flex: 1, padding: 12, borderWidth: 1, borderColor: "#000",
    borderRadius: 8, alignItems: "center",
  },
  addBtnText: { fontSize: 14, fontWeight: "600" },
  itemCount: { textAlign: "center", fontSize: 12, color: "#999", marginBottom: 12 },
  nextBtn: {
    backgroundColor: "#000", borderRadius: 12, padding: 16, alignItems: "center",
  },
  nextBtnDisabled: { opacity: 0.5 },
  nextBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
