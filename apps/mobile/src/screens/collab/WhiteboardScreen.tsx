/**
 * WhiteboardScreen — embeds tldraw inside a WebView with a postMessage bridge.
 *
 * Architecture (per plan §4):
 * - The whiteboard HTML page (tldraw + Y.js + y-websocket provider) is served
 *   from CloudFront or bundled via expo-asset.
 * - RN acts as a thin host: injects INIT payload, handles bridge messages.
 * - Touch passthrough: scrollEnabled={false} prevents ScrollView from stealing gestures.
 *
 * Bridge protocol (§4.2):
 *   RN → WebView:  INIT | EXPORT_REQUEST | SET_READONLY | FOCUS_SHAPE
 *   WebView → RN:  READY | EXPORT_RESULT | EXPORT_ERROR | PRESENCE_UPDATE | ERROR
 */

import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import WebView, { WebViewMessageEvent } from 'react-native-webview';
import { useNavigation, useRoute } from '@react-navigation/native';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BridgeMessage {
  type: string;
  requestId?: string;
  payload?: unknown;
}

interface RouteParams {
  collabId: string;
  authToken: string;
  userId: string;
  isReadOnly?: boolean;
}

interface ExportOptions {
  format: 'png' | 'pdf';
  resolution: 'basic' | 'hi';
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// In production this URL points to the CloudFront-hosted whiteboard.html.
// Falls back to a bundled asset for offline/CI scenarios.
const WHITEBOARD_BASE_URL =
  process.env.EXPO_PUBLIC_WHITEBOARD_URL ?? 'https://cdn.example.com/whiteboard/index.html';

// ---------------------------------------------------------------------------
// WhiteboardScreen
// ---------------------------------------------------------------------------

export default function WhiteboardScreen() {
  const navigation = useNavigation();
  const route = useRoute();
  const { collabId, authToken, userId, isReadOnly = false } =
    route.params as RouteParams;

  const webViewRef = useRef<WebView>(null);
  const [isReady, setIsReady] = useState(false);
  const [onlineUsers, setOnlineUsers] = useState<string[]>([userId]);
  const [exportPending, setExportPending] = useState(false);
  const pendingExports = useRef<Map<string, (result: string) => void>>(new Map());

  // -----------------------------------------------------------------------
  // WebView → RN message handler
  // -----------------------------------------------------------------------

  const handleMessage = useCallback(
    (event: WebViewMessageEvent) => {
      let msg: BridgeMessage;
      try {
        msg = JSON.parse(event.nativeEvent.data);
      } catch {
        return;
      }

      switch (msg.type) {
        case 'READY': {
          setIsReady(true);
          // After ready, send current readonly state if needed
          if (isReadOnly) {
            _injectMessage(webViewRef, { type: 'SET_READONLY', payload: { readonly: true } });
          }
          break;
        }

        case 'PRESENCE_UPDATE': {
          const p = msg.payload as { onlineUserIds: string[] };
          setOnlineUsers(p.onlineUserIds ?? []);
          break;
        }

        case 'EXPORT_RESULT': {
          const p = msg.payload as { requestId: string; dataUri: string; mimeType: string };
          const resolve = pendingExports.current.get(p.requestId);
          if (resolve) {
            pendingExports.current.delete(p.requestId);
            resolve(p.dataUri);
          }
          setExportPending(false);
          break;
        }

        case 'EXPORT_ERROR': {
          const p = msg.payload as { requestId: string; error: string };
          pendingExports.current.delete(p.requestId);
          setExportPending(false);
          console.warn('[Whiteboard] Export error:', p.error);
          break;
        }

        case 'ERROR': {
          const p = msg.payload as { code: string; message: string };
          console.error('[Whiteboard] WS error:', p.code, p.message);
          break;
        }
      }
    },
    [isReadOnly],
  );

  // -----------------------------------------------------------------------
  // Inject INIT after WebView loads
  // -----------------------------------------------------------------------

  const handleLoadEnd = useCallback(() => {
    _injectMessage(webViewRef, {
      type: 'INIT',
      payload: {
        collabId,
        authToken,
        userId,
        resolution: 'basic',
      },
    });
  }, [collabId, authToken, userId]);

  // -----------------------------------------------------------------------
  // Export handler (called from header button)
  // -----------------------------------------------------------------------

  const handleExport = useCallback(
    async (options: ExportOptions) => {
      if (!isReady || exportPending) return;
      setExportPending(true);

      const requestId = Math.random().toString(36).slice(2);

      const result = await new Promise<string>((resolve) => {
        pendingExports.current.set(requestId, resolve);
        _injectMessage(webViewRef, {
          type: 'EXPORT_REQUEST',
          requestId,
          payload: { requestId, format: options.format, resolution: options.resolution },
        });

        // Timeout safety
        setTimeout(() => {
          if (pendingExports.current.has(requestId)) {
            pendingExports.current.delete(requestId);
            setExportPending(false);
          }
        }, 15_000);
      });

      // Upload via media-svc or direct S3 presign (handled elsewhere)
      console.log('[Whiteboard] Export data URI received, length:', result.length);
    },
    [isReady, exportPending],
  );

  // -----------------------------------------------------------------------
  // Build WebView source URL with auth
  // -----------------------------------------------------------------------

  const whiteboardUrl = `${WHITEBOARD_BASE_URL}?collabId=${encodeURIComponent(collabId)}`;

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Co-presence indicator */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>

        <View style={styles.presenceRow}>
          {onlineUsers.map((uid) => (
            <View key={uid} style={styles.presenceDot} />
          ))}
          <Text style={styles.presenceCount}>{onlineUsers.length} online</Text>
        </View>

        {!isReadOnly && (
          <TouchableOpacity
            onPress={() => handleExport({ format: 'png', resolution: 'basic' })}
            disabled={exportPending || !isReady}
            style={[styles.exportButton, (!isReady || exportPending) && styles.exportButtonDisabled]}
          >
            <Text style={styles.exportText}>{exportPending ? '…' : 'Export'}</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Loading overlay */}
      {!isReady && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" />
          <Text style={styles.loadingText}>Loading whiteboard…</Text>
        </View>
      )}

      {/* tldraw WebView */}
      <WebView
        ref={webViewRef}
        source={{ uri: whiteboardUrl }}
        style={styles.webView}
        // Touch passthrough — prevent RN scroll from stealing gestures
        scrollEnabled={false}
        bounces={false}
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
        keyboardDisplayRequiresUserAction={false}
        // Message bridge
        onMessage={handleMessage}
        onLoadEnd={handleLoadEnd}
        // Allow mixed content for local dev
        mixedContentMode="always"
        // Prevent rubber-banding on iOS
        contentInset={{ top: 0, left: 0, bottom: 0, right: 0 }}
      />
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _injectMessage(
  ref: React.RefObject<WebView>,
  msg: BridgeMessage,
): void {
  const json = JSON.stringify(msg).replace(/\\/g, '\\\\').replace(/`/g, '\\`');
  ref.current?.injectJavaScript(
    `(function(){window.__rnBridge&&window.__rnBridge.receive(\`${json}\`);})();true;`,
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e0e0e0',
    backgroundColor: '#fff',
  },
  backButton: {
    marginRight: 12,
  },
  backText: {
    fontSize: 16,
    color: '#007AFF',
  },
  presenceRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  presenceDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#34C759',
  },
  presenceCount: {
    fontSize: 13,
    color: '#666',
  },
  exportButton: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: '#007AFF',
    borderRadius: 8,
  },
  exportButtonDisabled: {
    opacity: 0.4,
  },
  exportText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  webView: {
    flex: 1,
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.9)',
    zIndex: 10,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: '#666',
  },
});
