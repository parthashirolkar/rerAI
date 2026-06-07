import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, usePaginatedQuery } from "convex/react";
import { api } from "@/lib/convexApi";
import type { Id } from "@convex-generated/dataModel";
import type { ChatMessage, ConversationTurn } from "@/lib/messages";
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
  const paginatedTurns = usePaginatedQuery(
    api.turns.listByThread,
    viewerReady && activeThreadId ? { threadId: activeThreadId as Id<"uiThreads"> } : "skip",
    { initialNumItems: 20 },
  );

  const threads = useMemo(() => (threadsResult ?? []) as Thread[], [threadsResult]);

  const turns = useMemo(() => {
    const results = (paginatedTurns.results ?? []) as ConversationTurn[];
    return [...results].sort(
      (left, right) => left.turnPosition - right.turnPosition,
    );
  }, [paginatedTurns.results]);
  const messages = useMemo<ChatMessage[]>(
    () =>
      turns.flatMap((turn) => [
        {
          id: turn.turnId,
          role: "user" as const,
          content: turn.userContent,
          createdAt: turn.createdAt,
        },
        ...turn.assistantMessages.map((message) => ({
          id: message.id,
          langgraphMessageId: message.langgraphMessageId,
          role: "assistant" as const,
          content: `${message.canonicalContent}${message.displayOnlyContent ?? ""}`,
          createdAt: message.createdAt,
          messagePosition: message.messagePosition,
        })),
      ]),
    [turns],
  );
  const runState = useMemo<RunState | null>(() => {
    const latest = turns.at(-1);
    if (!latest) {
      return null;
    }
    if (latest.status === "pending" || latest.status === "running") {
      return { status: "running" };
    }
    if (latest.status === "failed") {
      return { status: "error", errorMessage: latest.errorMessage };
    }
    return { status: "idle" };
  }, [turns]);

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
      runState,
      messages,
      turns,
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
      turns,
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
