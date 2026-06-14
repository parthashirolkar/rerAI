import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, usePaginatedQuery } from "convex/react";
import { api } from "@/lib/convexApi";
import type { Id } from "@convex-generated/dataModel";
import type { ChatMessage, ConversationTurn } from "@/lib/messages";
import type { BackendPort, Thread, Viewer } from "../ports";

export function useConvexBackendAdapter(viewerReady: boolean): BackendPort {
  const [activeThreadId, setActiveThread] = useState<string | null>(null);

  const ensureViewer = useMutation(api.users.ensureViewer);
  const createThread = useMutation(api.threads.create);
  const removeThread = useMutation(api.threads.remove);
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

  return useMemo(
    () => ({
      viewer: viewer as Viewer | null | undefined,
      threads,
      messages,
      turns,
      setActiveThread,
      ensureViewer: ensureViewerFn,
      createThread: createThreadFn,
      removeThread: removeThreadFn,
    }),
    [
      viewer,
      threads,
      messages,
      turns,
      setActiveThread,
      ensureViewerFn,
      createThreadFn,
      removeThreadFn,
    ],
  );
}
