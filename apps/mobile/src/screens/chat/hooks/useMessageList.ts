/**
 * useMessageList — manages the message list state for a chat room.
 *
 * - Loads initial messages via REST pagination
 * - Merges real-time WS messages + replays
 * - Tracks optimistic (pending) messages
 * - Provides infinite scroll upward (older messages)
 */

import { useCallback, useReducer, useRef } from "react";
import { getMessages, type ChatMessageOut } from "../../../api/chat";

export interface OptimisticMessage extends ChatMessageOut {
  isPending?: boolean;
}

interface MessageState {
  messages: OptimisticMessage[];
  olderCursor: string | null;
  hasMore: boolean;
  loadingOlder: boolean;
  initialLoaded: boolean;
}

type Action =
  | { type: "INITIAL_LOAD"; messages: OptimisticMessage[]; nextCursor: string | null }
  | { type: "PREPEND_OLDER"; messages: OptimisticMessage[]; nextCursor: string | null }
  | { type: "APPEND"; message: OptimisticMessage }
  | { type: "MERGE_REPLAY"; messages: ChatMessageOut[] }
  | { type: "CONFIRM_OPTIMISTIC"; clientNonce: string; confirmed: ChatMessageOut }
  | { type: "SET_LOADING_OLDER"; loading: boolean };

function messagesReducer(state: MessageState, action: Action): MessageState {
  switch (action.type) {
    case "INITIAL_LOAD":
      return {
        ...state,
        messages: action.messages,
        olderCursor: action.nextCursor,
        hasMore: !!action.nextCursor,
        initialLoaded: true,
      };

    case "PREPEND_OLDER":
      return {
        ...state,
        messages: [...action.messages, ...state.messages],
        olderCursor: action.nextCursor,
        hasMore: !!action.nextCursor,
        loadingOlder: false,
      };

    case "APPEND": {
      // Deduplicate by id or client_nonce
      const exists = state.messages.some(
        (m) => m.id === action.message.id
      );
      if (exists) return state;
      return { ...state, messages: [...state.messages, action.message] };
    }

    case "MERGE_REPLAY": {
      const existingIds = new Set(state.messages.map((m) => m.id));
      const newMsgs = action.messages.filter((m) => !existingIds.has(m.id));
      return {
        ...state,
        messages: [...state.messages, ...newMsgs],
      };
    }

    case "CONFIRM_OPTIMISTIC": {
      return {
        ...state,
        messages: state.messages.map((m) => {
          if (m.client_nonce === action.clientNonce && m.isPending) {
            return { ...action.confirmed, isPending: false };
          }
          return m;
        }),
      };
    }

    case "SET_LOADING_OLDER":
      return { ...state, loadingOlder: action.loading };

    default:
      return state;
  }
}

const initialState: MessageState = {
  messages: [],
  olderCursor: null,
  hasMore: false,
  loadingOlder: false,
  initialLoaded: false,
};

export function useMessageList(roomId: string) {
  const [state, dispatch] = useReducer(messagesReducer, initialState);

  const loadInitial = useCallback(async () => {
    const result = await getMessages(roomId, { limit: 50, direction: "before" });
    dispatch({
      type: "INITIAL_LOAD",
      messages: result.messages as OptimisticMessage[],
      nextCursor: result.next_cursor ?? null,
    });
  }, [roomId]);

  const loadOlder = useCallback(async () => {
    if (state.loadingOlder || !state.hasMore || !state.olderCursor) return;
    dispatch({ type: "SET_LOADING_OLDER", loading: true });
    try {
      const result = await getMessages(roomId, {
        limit: 50,
        direction: "before",
        cursor: state.olderCursor,
      });
      dispatch({
        type: "PREPEND_OLDER",
        messages: result.messages as OptimisticMessage[],
        nextCursor: result.next_cursor ?? null,
      });
    } catch {
      dispatch({ type: "SET_LOADING_OLDER", loading: false });
    }
  }, [roomId, state.loadingOlder, state.hasMore, state.olderCursor]);

  const appendMessage = useCallback((msg: ChatMessageOut, isPending = false) => {
    dispatch({ type: "APPEND", message: { ...msg, isPending } });
  }, []);

  const mergeReplay = useCallback((msgs: ChatMessageOut[]) => {
    dispatch({ type: "MERGE_REPLAY", messages: msgs });
  }, []);

  const confirmOptimistic = useCallback(
    (clientNonce: string, confirmed: ChatMessageOut) => {
      dispatch({ type: "CONFIRM_OPTIMISTIC", clientNonce, confirmed });
    },
    []
  );

  return {
    messages: state.messages,
    hasMore: state.hasMore,
    loadingOlder: state.loadingOlder,
    initialLoaded: state.initialLoaded,
    loadInitial,
    loadOlder,
    appendMessage,
    mergeReplay,
    confirmOptimistic,
  };
}
