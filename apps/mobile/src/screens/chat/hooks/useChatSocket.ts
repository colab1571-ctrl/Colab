/**
 * useChatSocket — WebSocket connection manager for a single chat room.
 *
 * Implements §4 reconnect+resume protocol:
 * - Exponential backoff reconnect (1s, 2s, 4s… cap 60s)
 * - `since_msg_id` replay on reconnect
 * - `pending_sends` queue drained after replay
 * - Application-level ping every 8 minutes to beat API GW idle timeout
 * - `connection_expiry_warning` → proactive reconnect at 115min mark
 *
 * Returns:
 *   sendMessage(body, replyTo?, clientNonce?) → void (optimistic)
 *   sendTyping(state: "start" | "stop") → void
 *   sendReadAck(upToMsgId: string) → void
 *   isConnected: boolean
 *   connectionState: "connecting" | "open" | "closed"
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useEffect, useRef, useState } from "react";
import "react-native-get-random-values";
import { v4 as uuidv4 } from "uuid";

import { getChatWsUrl, type ChatMessageOut } from "../../../api/chat";

const PING_INTERVAL_MS = 8 * 60 * 1000; // 8 minutes
const MAX_BACKOFF_MS = 60_000;
const PENDING_QUEUE_KEY = (roomId: string) => `chat:pending:${roomId}`;
const LAST_ACK_KEY = (roomId: string) => `chat:last_ack:${roomId}`;

export type WSConnectionState = "connecting" | "open" | "closed";

export interface PendingSend {
  body: string;
  reply_to?: string;
  client_nonce: string;
  timestamp: string;
}

export interface UseChatSocketOptions {
  roomId: string;
  profileId: string;
  onMessage: (msg: ChatMessageOut) => void;
  onReplay: (msgs: ChatMessageOut[], hasMore: boolean) => void;
  onTyping: (profileId: string, state: "start" | "stop") => void;
  onPresence: (profileId: string, online: boolean, lastSeenAt: string) => void;
  onRead: (profileId: string, upToMsgId: string, readAt: string) => void;
  onRoomState: (state: "open" | "read_only" | "archived") => void;
  onError?: (code: string, message: string) => void;
}

export function useChatSocket(options: UseChatSocketOptions) {
  const {
    roomId,
    profileId,
    onMessage,
    onReplay,
    onTyping,
    onPresence,
    onRead,
    onRoomState,
    onError,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const [connectionState, setConnectionState] = useState<WSConnectionState>("connecting");
  const isMounted = useRef(true);

  // -------------------------------------------------------------------------
  // Pending queue helpers
  // -------------------------------------------------------------------------

  const enqueuePending = useCallback(async (send: PendingSend) => {
    const key = PENDING_QUEUE_KEY(roomId);
    const raw = await AsyncStorage.getItem(key);
    const queue: PendingSend[] = raw ? JSON.parse(raw) : [];
    queue.push(send);
    await AsyncStorage.setItem(key, JSON.stringify(queue));
  }, [roomId]);

  const drainPendingQueue = useCallback(async (ws: WebSocket) => {
    const key = PENDING_QUEUE_KEY(roomId);
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return;
    const queue: PendingSend[] = JSON.parse(raw);
    for (const pending of queue) {
      ws.send(JSON.stringify({
        type: "send",
        payload: {
          body: pending.body,
          reply_to: pending.reply_to,
          client_nonce: pending.client_nonce,
        },
        request_id: uuidv4(),
        ts: new Date().toISOString(),
      }));
    }
    await AsyncStorage.removeItem(key);
  }, [roomId]);

  const saveLastAck = useCallback(async (msgId: string) => {
    await AsyncStorage.setItem(LAST_ACK_KEY(roomId), msgId);
  }, [roomId]);

  const getLastAck = useCallback(async (): Promise<string | null> => {
    return AsyncStorage.getItem(LAST_ACK_KEY(roomId));
  }, [roomId]);

  // -------------------------------------------------------------------------
  // Connection lifecycle
  // -------------------------------------------------------------------------

  const connect = useCallback(async () => {
    if (!isMounted.current) return;
    setConnectionState("connecting");

    const ws = new WebSocket(getChatWsUrl(roomId));
    wsRef.current = ws;

    ws.onopen = async () => {
      if (!isMounted.current) { ws.close(); return; }
      reconnectAttempts.current = 0;
      setConnectionState("open");

      // Send reconnect frame if we have a last ack
      const lastAck = await getLastAck();
      if (lastAck) {
        ws.send(JSON.stringify({
          type: "reconnect",
          payload: { since_msg_id: lastAck },
          request_id: uuidv4(),
          ts: new Date().toISOString(),
        }));
      }

      // Start keepalive ping every 8 minutes
      if (pingTimer.current) clearInterval(pingTimer.current);
      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping", payload: {}, ts: new Date().toISOString() }));
        }
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = async (event) => {
      let frame: { type: string; payload: Record<string, unknown> };
      try {
        frame = JSON.parse(event.data as string);
      } catch {
        return;
      }

      const { type, payload } = frame;

      switch (type) {
        case "message": {
          const msg = payload as unknown as ChatMessageOut;
          onMessage(msg);
          await saveLastAck(msg.id);
          break;
        }
        case "message_ack": {
          await saveLastAck(payload.msg_id as string);
          break;
        }
        case "replay": {
          const msgs = payload.messages as ChatMessageOut[];
          const hasMore = payload.has_more as boolean;
          onReplay(msgs, hasMore);
          if (msgs.length > 0) {
            await saveLastAck(msgs[msgs.length - 1].id);
          }
          // Drain pending queue after replay
          if (ws.readyState === WebSocket.OPEN) {
            await drainPendingQueue(ws);
          }
          break;
        }
        case "typing": {
          onTyping(payload.profile_id as string, payload.state as "start" | "stop");
          break;
        }
        case "presence": {
          onPresence(
            payload.profile_id as string,
            payload.online as boolean,
            payload.last_seen_at as string
          );
          break;
        }
        case "read": {
          onRead(
            payload.profile_id as string,
            payload.up_to_msg_id as string,
            payload.read_at as string
          );
          break;
        }
        case "room_state": {
          onRoomState(payload.state as "open" | "read_only" | "archived");
          break;
        }
        case "connection_expiry_warning": {
          // Proactive reconnect: open new WS, then close old
          const newWs = new WebSocket(getChatWsUrl(roomId));
          wsRef.current = newWs;
          setTimeout(() => {
            if (ws.readyState === WebSocket.OPEN) ws.close(1000, "expiry_reconnect");
          }, 1000);
          break;
        }
        case "error": {
          onError?.(payload.code as string, payload.message as string);
          break;
        }
        case "pong":
          break;
        default:
          break;
      }
    };

    ws.onclose = () => {
      if (!isMounted.current) return;
      setConnectionState("closed");
      if (pingTimer.current) clearInterval(pingTimer.current);

      // Exponential backoff reconnect
      const attempt = reconnectAttempts.current;
      const delay = Math.min(1000 * Math.pow(2, attempt), MAX_BACKOFF_MS);
      reconnectAttempts.current += 1;

      reconnectTimer.current = setTimeout(() => {
        if (isMounted.current) connect();
      }, delay);
    };

    ws.onerror = () => {
      // onclose will fire after onerror — reconnect handled there
    };
  }, [roomId, getLastAck, saveLastAck, drainPendingQueue, onMessage, onReplay, onTyping, onPresence, onRead, onRoomState, onError]);

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  const sendMessage = useCallback(
    async (body: string, replyTo?: string) => {
      const clientNonce = uuidv4();
      const frame = {
        type: "send",
        payload: { body, reply_to: replyTo, client_nonce: clientNonce },
        request_id: uuidv4(),
        ts: new Date().toISOString(),
      };

      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(frame));
      } else {
        // Offline: queue for later
        await enqueuePending({
          body,
          reply_to: replyTo,
          client_nonce: clientNonce,
          timestamp: new Date().toISOString(),
        });
      }
      return clientNonce;
    },
    [enqueuePending]
  );

  const sendTyping = useCallback((state: "start" | "stop") => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "typing",
        payload: { state },
        ts: new Date().toISOString(),
      }));
    }
  }, []);

  const sendReadAck = useCallback((upToMsgId: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "read_ack",
        payload: { up_to_msg_id: upToMsgId },
        ts: new Date().toISOString(),
      }));
    }
  }, []);

  // -------------------------------------------------------------------------
  // Mount / unmount
  // -------------------------------------------------------------------------

  useEffect(() => {
    isMounted.current = true;
    connect();

    return () => {
      isMounted.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (pingTimer.current) clearInterval(pingTimer.current);
      wsRef.current?.close(1000, "unmount");
    };
  }, [roomId]); // Reconnect when roomId changes

  return {
    connectionState,
    isConnected: connectionState === "open",
    sendMessage,
    sendTyping,
    sendReadAck,
  };
}
