import { useMemo } from "react";
import { useStream } from "@langchain/react";
import { ASSISTANT_ID, createLangGraphClient } from "@/lib/langgraphClient";
import type { StreamState, UseStreamAdapter } from "../ports";

export const useLangGraphStreamAdapter: UseStreamAdapter = (
  { authToken, threadId },
  callbacks,
): StreamState => {
  const client = useMemo(() => createLangGraphClient(authToken), [authToken]);

  const rawStream = useStream<Record<string, unknown>>({
    client,
    assistantId: ASSISTANT_ID,
    threadId,
    fetchStateHistory: true,
    reconnectOnMount: true,
    onThreadId(nextThreadId) {
      callbacks.onThreadId?.(nextThreadId);
    },
    onCreated(run) {
      callbacks.onCreated?.(run);
    },
    onFinish(state) {
      callbacks.onFinish?.(state);
    },
    onStop() {
      callbacks.onStop?.();
    },
    async onError(error) {
      callbacks.onError?.(error);
    },
  });

  return useMemo(
    () => ({
      messages: rawStream.messages,
      isLoading: rawStream.isLoading,
      error: rawStream.error instanceof Error ? rawStream.error : null,
      interrupts: rawStream.interrupts,
      switchThread: rawStream.switchThread,
      submit: rawStream.submit,
      stop: rawStream.stop,
    }),
    [
      rawStream.messages,
      rawStream.isLoading,
      rawStream.error,
      rawStream.interrupts,
      rawStream.switchThread,
      rawStream.submit,
      rawStream.stop,
    ],
  );
};
