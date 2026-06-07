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
    fetchStateHistory: false,
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
      messages: rawStream.messages.map((message, index) => ({
        data: message,
        messagePosition: rawStream.getMessagesMetadata(message, index)
          ?.streamMetadata?.message_position,
      })),
      isLoading: rawStream.isLoading,
      error: rawStream.error instanceof Error ? rawStream.error : null,
      interrupts: rawStream.interrupts,
      switchThread: rawStream.switchThread,
      joinStream: rawStream.joinStream,
      submit: rawStream.submit,
      stop: rawStream.stop,
    }),
    [
      rawStream.messages,
      rawStream.getMessagesMetadata,
      rawStream.isLoading,
      rawStream.error,
      rawStream.interrupts,
      rawStream.switchThread,
      rawStream.joinStream,
      rawStream.submit,
      rawStream.stop,
    ],
  );
};
