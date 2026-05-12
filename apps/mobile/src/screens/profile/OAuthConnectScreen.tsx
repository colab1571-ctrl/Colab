/**
 * OAuth Connect Screen — link Instagram / YouTube / Spotify.
 *
 * Flow:
 *   1. POST /api/v1/profile/me/externals/{provider}/connect → authorize_url
 *   2. Open in-app browser (WebBrowser)
 *   3. App receives deep link colab://profile/externals?status=connected&provider=...
 *   4. Update UI; tokens never visible client-side
 */

import React, { useState } from "react";
import {
  Linking,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

type Props = {
  navigation: NativeStackNavigationProp<any, "OAuthConnect">;
};

type Provider = "instagram" | "youtube" | "spotify";

interface ProviderState {
  connected: boolean;
  handle: string | null;
  syncing: boolean;
}

const PROVIDER_META: Record<Provider, { label: string; color: string }> = {
  instagram: { label: "Instagram", color: "#E1306C" },
  youtube: { label: "YouTube", color: "#FF0000" },
  spotify: { label: "Spotify for Artists", color: "#1DB954" },
};

export function OAuthConnectScreen({ navigation }: Props): React.ReactElement {
  const [providers, setProviders] = useState<Record<Provider, ProviderState>>({
    instagram: { connected: false, handle: null, syncing: false },
    youtube: { connected: false, handle: null, syncing: false },
    spotify: { connected: false, handle: null, syncing: false },
  });

  const handleConnect = async (provider: Provider) => {
    setProviders((prev) => ({
      ...prev,
      [provider]: { ...prev[provider], syncing: true },
    }));

    try {
      // 1. Get authorize URL from profile-svc
      // const { authorize_url } = await profileApi.connectProvider(provider);
      // 2. Open in WebBrowser; receives deep link on return
      // await WebBrowser.openAuthSessionAsync(authorize_url, "colab://profile/externals");
      // Stub: mark as connected
      setTimeout(() => {
        setProviders((prev) => ({
          ...prev,
          [provider]: { connected: true, handle: `@stub_${provider}`, syncing: false },
        }));
      }, 1500);
    } catch (err: any) {
      setProviders((prev) => ({
        ...prev,
        [provider]: { ...prev[provider], syncing: false },
      }));
    }
  };

  const handleDisconnect = async (provider: Provider) => {
    setProviders((prev) => ({
      ...prev,
      [provider]: { connected: false, handle: null, syncing: false },
    }));
    // TODO: DELETE /api/v1/profile/me/externals/{provider}
  };

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Connect your socials</Text>
      <Text style={styles.subheading}>
        Optional. Verified links show on your public profile and signal authenticity.
        We never post on your behalf.
      </Text>

      {(Object.entries(PROVIDER_META) as [Provider, { label: string; color: string }][]).map(
        ([provider, meta]) => {
          const state = providers[provider];
          return (
            <View key={provider} style={styles.providerRow}>
              <View style={[styles.providerIcon, { backgroundColor: meta.color }]}>
                <Text style={styles.providerIconText}>{meta.label[0]}</Text>
              </View>
              <View style={styles.providerInfo}>
                <Text style={styles.providerLabel}>{meta.label}</Text>
                {state.connected && state.handle && (
                  <Text style={styles.providerHandle}>{state.handle}</Text>
                )}
              </View>
              {state.connected ? (
                <TouchableOpacity
                  style={styles.disconnectBtn}
                  onPress={() => handleDisconnect(provider)}
                >
                  <Text style={styles.disconnectBtnText}>Disconnect</Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity
                  style={[styles.connectBtn, state.syncing && styles.connectBtnDisabled]}
                  onPress={() => handleConnect(provider)}
                  disabled={state.syncing}
                >
                  <Text style={styles.connectBtnText}>
                    {state.syncing ? "Connecting…" : "Connect"}
                  </Text>
                </TouchableOpacity>
              )}
            </View>
          );
        }
      )}

      <TouchableOpacity
        style={styles.nextBtn}
        onPress={() => navigation.navigate("ProfileView" as never)}
      >
        <Text style={styles.nextBtnText}>Finish setup</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", padding: 24 },
  heading: { fontSize: 24, fontWeight: "700", marginBottom: 8 },
  subheading: { fontSize: 14, color: "#666", marginBottom: 28 },
  providerRow: {
    flexDirection: "row", alignItems: "center", padding: 16,
    borderWidth: 1, borderColor: "#eee", borderRadius: 12, marginBottom: 12,
  },
  providerIcon: {
    width: 44, height: 44, borderRadius: 22, alignItems: "center",
    justifyContent: "center", marginRight: 12,
  },
  providerIconText: { color: "#fff", fontSize: 20, fontWeight: "700" },
  providerInfo: { flex: 1 },
  providerLabel: { fontSize: 16, fontWeight: "600" },
  providerHandle: { fontSize: 13, color: "#666", marginTop: 2 },
  connectBtn: {
    backgroundColor: "#000", borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8,
  },
  connectBtnDisabled: { opacity: 0.5 },
  connectBtnText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  disconnectBtn: {
    borderWidth: 1, borderColor: "#ddd", borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8,
  },
  disconnectBtnText: { fontSize: 13, color: "#999" },
  nextBtn: {
    backgroundColor: "#000", borderRadius: 12, padding: 16,
    alignItems: "center", marginTop: "auto",
  },
  nextBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
