/**
 * MediaImage — renders an image thumbnail in the chat bubble.
 * Tap to open full-screen lightbox (pinch-to-zoom).
 * Spec: T-52 (image picker thumbnail), T-53 (ImageLightbox)
 */

import { Image } from "expo-image";
import React, { useState } from "react";
import {
  Dimensions,
  Modal,
  StyleSheet,
  TouchableOpacity,
  View,
} from "react-native";

const { width: SCREEN_WIDTH } = Dimensions.get("window");
const THUMB_SIZE = Math.min(240, SCREEN_WIDTH * 0.55);

interface Props {
  mediaUrl: string;
}

export function MediaImage({ mediaUrl }: Props) {
  const [lightboxOpen, setLightboxOpen] = useState(false);

  return (
    <>
      <TouchableOpacity onPress={() => setLightboxOpen(true)} activeOpacity={0.9}>
        <Image
          source={{ uri: mediaUrl }}
          style={styles.thumbnail}
          contentFit="cover"
          transition={150}
        />
      </TouchableOpacity>

      {/* Full-screen lightbox */}
      <Modal visible={lightboxOpen} animationType="fade" transparent>
        <View style={styles.lightbox}>
          <TouchableOpacity style={styles.lightboxClose} onPress={() => setLightboxOpen(false)}>
            <View style={styles.closeBtn}>
              <Image
                source={{ uri: mediaUrl }}
                style={styles.lightboxImage}
                contentFit="contain"
              />
            </View>
          </TouchableOpacity>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  thumbnail: {
    width: THUMB_SIZE,
    height: THUMB_SIZE * 0.75,
    borderRadius: 12,
    backgroundColor: "#E0E0E0",
  },
  lightbox: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.92)",
    justifyContent: "center",
    alignItems: "center",
  },
  lightboxClose: { flex: 1, width: "100%", justifyContent: "center", alignItems: "center" },
  closeBtn: { width: "100%", height: "100%", justifyContent: "center", alignItems: "center" },
  lightboxImage: {
    width: SCREEN_WIDTH,
    height: SCREEN_WIDTH,
  },
});
