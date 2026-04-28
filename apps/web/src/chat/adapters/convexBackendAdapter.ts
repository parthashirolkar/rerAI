import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, usePaginatedQuery } from "convex/react";
import { api } from "@/lib/convexApi";
import type { Id } from "@convex-generated/dataModel";
import type { ChatMessage } from "@/lib/messages";
import type { BackendPort, Thread, Viewer, RunState } from "../ports";

export function useConvexBackendAdapter(viewerReady: boolean): BackendPort {
  const [activeThreadId, setActiveThread] = useState<string | null>(null);

  const ensureViewer = useMutation(api.users.ensureViewer);
  const createThread = useMutation(api.threads.create);
  const removeThread = useMutation(api.threads.remove);
  const attachLangGraphThread = useMutation(api.threads.attachLangGraphThread);
  const detachLangGraphThread = useMutation(api.threads.detachLangGraphThread);
  const appendUserMessage = useMutation(api.messages.appendUserMessage);
  const syncAssistantMessages = useMutation(api.messages.syncAssistantMessages);
  const setRunning = useMutation(api.runState.setRunning);
  const setError = useMutation(api.runState.setError);
  const setIdle = useMutation(api.runState.setIdle);

  const viewer = useQuery(api.users.getCurrent, viewerReady ? {} : "skip");
  const threadsResult = useQuery(api.threads.listMine, viewerReady ? {} : "skip");
  const runState = useQuery(
    api.runState.getForThread,
    viewerReady && activeThreadId ? { threadId: activeThreadId as Id<"uiThreads"> } : "skip",
  );
  const paginatedMessages = usePaginatedQuery(
    api.messages.listByThread,
    viewerReady && activeThreadId ? { threadId: activeThreadId as Id<"uiThreads"> } : "skip",
    { initialNumItems: 50 },
  );

  const threads = useMemo(() => (threadsResult ?? []) as Thread[], [threadsResult]);

  const messages = useMemo(() => {
    const results = (paginatedMessages.results ?? []) as Array<
      ChatMessage & { langgraphMessageId?: string }
    >;
    return results
      .map((message) => ({
        ...message,
        id: message.id ?? message.langgraphMessageId,
      }))
      .sort((left, right) => left.createdAt - right.createdAt);
  }, [paginatedMessages.results]);

  const ensureViewerFn = useCallback(async () => {
    await ensureViewer({});
  }, [ensureViewer]);

  const createThreadFn = useCallback(async () => {
    return (await createThread({})) as Thread;
  }, [createThread]);

  const removeThreadFn = useCallback(
    async (threadId: string) => {
      await removeThread({ threadId: threadId as Id<"uiThreads"> });
    },
    [removeThread],
  );

  const attachLangGraphThreadFn = useCallback(
    async (threadId: string, langgraphThreadId: string) => {
      await attachLangGraphThread({
        threadId: threadId as Id<"uiThreads">,
        langgraphThreadId,
      });
    },
    [attachLangGraphThread],
  );

  const detachLangGraphThreadFn = useCallback(
    async (threadId: string) => {
      await detachLangGraphThread({ threadId: threadId as Id<"uiThreads"> });
    },
    [detachLangGraphThread],
  );

  const appendUserMessageFn = useCallback(
    async (threadId: string, content: string) => {
      await appendUserMessage({
        threadId: threadId as Id<"uiThreads">,
        content,
      });
    },
    [appendUserMessage],
  );

  const syncAssistantMessagesFn = useCallback(
    async (threadId: string, msgs: Parameters<BackendPort["syncAssistantMessages"]>[1]) => {
      await syncAssistantMessages({
        threadId: threadId as Id<"uiThreads">,
        messages: msgs,
      });
    },
    [syncAssistantMessages],
  );

  const setRunningFn = useCallback(
    async (threadId: string, langgraphRunId?: string) => {
      await setRunning({
        threadId: threadId as Id<"uiThreads">,
        langgraphRunId,
      });
    },
    [setRunning],
  );

  const setErrorFn = useCallback(
    async (threadId: string, errorMessage: string) => {
      await setError({
        threadId: threadId as Id<"uiThreads">,
        errorMessage,
      });
    },
    [setError],
  );

  const setIdleFn = useCallback(
    async (threadId: string) => {
      await setIdle({ threadId: threadId as Id<"uiThreads"> });
    },
    [setIdle],
  );

  return useMemo(
    () => ({
      viewer: viewer as Viewer | null | undefined,
      threads,
      runState: runState as RunState | null | undefined,
      messages,
      setActiveThread,
      ensureViewer: ensureViewerFn,
      createThread: createThreadFn,
      removeThread: removeThreadFn,
      attachLangGraphThread: attachLangGraphThreadFn,
      detachLangGraphThread: detachLangGraphThreadFn,
      appendUserMessage: appendUserMessageFn,
      syncAssistantMessages: syncAssistantMessagesFn,
      setRunning: setRunningFn,
      setError: setErrorFn,
      setIdle: setIdleFn,
    }),
    [
      viewer,
      threads,
      runState,
      messages,
      setActiveThread,
      ensureViewerFn,
      createThreadFn,
      removeThreadFn,
      attachLangGraphThreadFn,
      detachLangGraphThreadFn,
      appendUserMessageFn,
      syncAssistantMessagesFn,
      setRunningFn,
      setErrorFn,
      setIdleFn,
    ],
  );
}
