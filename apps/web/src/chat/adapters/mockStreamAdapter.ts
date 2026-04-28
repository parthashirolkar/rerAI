import { useState, useCallback } from "react";
import type { StreamState, StreamCallbacks } from "../ports";

export function createMockStreamAdapter(
  overrides?: Partial<StreamState>,
): StreamState {
  return {
    messages: [],
    isLoading: false,
    error: null,
    interrupts: [],
    switchThread: () => {},
    submit: async () => {},
    stop: () => {},
    ...overrides,
  };
}

export function useMockStreamAdapter(
  config: { authToken: string | null; threadId: string | null },
  callbacks: StreamCallbacks,
): StreamState {
  const [state, setState] = useState<Omit<StreamState, "switchThread" | "submit" | "stop">>({
    messages: [],
    isLoading: false,
    error: null,
    interrupts: [],
  });

  const switchThread = useCallback(
    (id: string | null) => {
      if (id) {
        callbacks.onThreadId?.(id);
      }
      setState((prev) => ({ ...prev, messages: [], isLoading: false, error: null }));
    },
    [callbacks],
  );

  const submit = useCallback(
    async (payload: Parameters<StreamState["submit"]>[0]) => {
      setState((prev) => ({ ...prev, isLoading: true, error: null }));
      callbacks.onCreated?.({ run_id: "mock-run-1" });
      // Simulate stream finishing
      setTimeout(() => {
        setState((prev) => ({ ...prev, isLoading: false }));
        callbacks.onFinish?.({ values: { messages: payload.messages } });
      }, 10);
    },
    [callbacks],
  );

  const stop = useCallback(() => {
    setState((prev) => ({ ...prev, isLoading: false }));
    callbacks.onStop?.();
  }, [callbacks]);

  return {
    ...state,
    switchThread,
    submit,
    stop,
  };
}
