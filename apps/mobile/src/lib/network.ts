/**
 * Network state + offline queue infrastructure (NFR-7).
 * Full implementation in spec 007 (chat-svc). This module exposes the hook shape.
 */

import { useEffect, useState } from "react";

// Stub NetInfo — will be replaced with @react-native-community/netinfo in P2
export function useIsOnline(): boolean {
  const [online, setOnline] = useState(true);
  // TODO P2: wire NetInfo listener
  return online;
}

export interface QueuedWrite {
  id: string;
  endpoint: string;
  method: string;
  body: unknown;
  timestamp: number;
}

// MMKV-backed queue will be wired in spec 007
const _queue: QueuedWrite[] = [];

export function enqueueWrite(write: Omit<QueuedWrite, "id" | "timestamp">): void {
  _queue.push({
    ...write,
    id: Math.random().toString(36).slice(2),
    timestamp: Date.now(),
  });
}

export function flushQueue(): Promise<void> {
  // Will be implemented in spec 007 (chat-svc)
  return Promise.resolve();
}
