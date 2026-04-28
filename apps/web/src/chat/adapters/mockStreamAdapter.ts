import { useState, useCallback, useEffect, useRef } from "react";
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
  const finishTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [state, setState] = useState<Omit<StreamState, "switchThread" | "submit" | "stop">>({
    messages: [],
    isLoading: false,
    error: null,
    interrupts: [],
  });

  useEffect(() => {
    return () => {
      if (finishTimerRef.current) {
        clearTimeout(finishTimerRef.current);
      }
    };
  }, []);

  const switchThread = useCallback(
    (id: string | null) => {
      if (id) {
        callbacks.onThreadId?.(id);
      }
      if (finishTimerRef.current) {
        clearTimeout(finishTimerRef.current);
        finishTimerRef.current = null;
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
      if (finishTimerRef.current) {
        clearTimeout(finishTimerRef.current);
      }
      finishTimerRef.current = setTimeout(() => {
        finishTimerRef.current = null;
        setState((prev) => ({ ...prev, isLoading: false }));
        callbacks.onFinish?.({ values: { messages: payload.messages } });
      }, 10);
    },
    [callbacks],
  );

  const stop = useCallback(() => {
    if (finishTimerRef.current) {
      clearTimeout(finishTimerRef.current);
      finishTimerRef.current = null;
    }
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
