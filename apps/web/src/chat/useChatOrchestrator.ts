import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  extractThreadMessages,
  normalizeMessages,
  selectLiveAssistantMessage,
  selectLiveAssistantMessages,
  toAssistantMirrorPayload,
} from "@/lib/messages";
import type { ChatMessage, ConversationTurn } from "@/lib/messages";
import type {
  UseChatOrchestratorOptions,
  ChatOrchestratorState,
  ChatOrchestratorActions,
} from "./ports";

type OptimisticMessage = ChatMessage & {
  localOnly: true;
  threadId: string;
};

type ActiveTurn = {
  turnId: string;
  humanMessageId: string;
  threadId: string;
  userContent: string;
  turnPosition: number;
  createdAt: number;
};

type SubmitTiming = {
  startedAt: number;
  marks: Array<{ label: string; at: number }>;
  firstChunkLogged: boolean;
};

function chatTimingEnabled() {
  return (
    import.meta.env.DEV ||
    globalThis.localStorage?.getItem("rerai:chatTimings") === "1"
  );
}

function createSubmitTiming(): SubmitTiming {
  return {
    startedAt: performance.now(),
    marks: [],
    firstChunkLogged: false,
  };
}

function markSubmitTiming(timing: SubmitTiming | null, label: string) {
  if (!timing) {
    return;
  }
  timing.marks.push({ label, at: performance.now() });
}

function logSubmitTiming(timing: SubmitTiming | null, label: string) {
  if (!timing || !chatTimingEnabled()) {
    return;
  }
  const rows = timing.marks.map((mark) => ({
    event: mark.label,
    msSinceSubmit: Math.round(mark.at - timing.startedAt),
  }));
  console.table([
    ...rows,
    { event: label, msSinceSubmit: Math.round(performance.now() - timing.startedAt) },
  ]);
}

function hasPersistedEquivalent(
  persistedMessages: ChatMessage[],
  message: OptimisticMessage,
) {
  return persistedMessages.some(
    (persistedMessage) =>
      persistedMessage.role === message.role &&
      persistedMessage.content.trim() === message.content.trim(),
  );
}

function orderTranscriptMessages(messages: ChatMessage[]) {
  return messages
    .map((message, index) => ({ message, index }))
    .sort((left, right) => {
      const timeDelta = left.message.createdAt - right.message.createdAt;
      return timeDelta === 0 ? left.index - right.index : timeDelta;
    })
    .map(({ message }) => message);
}

export function useChatOrchestrator({
  backend,
  persistence,
  useStream,
  authToken,
  turnApi,
}: UseChatOrchestratorOptions): ChatOrchestratorState & ChatOrchestratorActions {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [langgraphThreadId, setLanggraphThreadId] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState("");
  const [submitInFlight, setSubmitInFlight] = useState(false);
  const [optimisticMessages, setOptimisticMessages] = useState<OptimisticMessage[]>([]);
  const [activeTurn, setActiveTurn] = useState<ActiveTurn | null>(null);

  const selectedThreadIdRef = useRef<string | null>(selectedThreadId);
  const streamMessagesRef = useRef<unknown[]>([]);
  const handledInterruptCountRef = useRef(0);
  const submitTimingRef = useRef<SubmitTiming | null>(null);

  useEffect(() => {
    selectedThreadIdRef.current = selectedThreadId;
  }, [selectedThreadId]);

  // Sync active thread to backend adapter
  useEffect(() => {
    backend.setActiveThread(selectedThreadId);
  }, [backend, selectedThreadId]);

  const recoverBrokenLangGraphThread = useCallback(
    async (threadId: string | null, message: string) => {
      const isUnauthorizedThread =
        message.includes("Unauthorized LangGraph thread access") ||
        message.includes("Unauthorized thread access");
      if (!threadId || !isUnauthorizedThread) {
        return false;
      }

      try {
        await backend.detachLangGraphThread(threadId);
      } catch (error) {
        setStatusNote(error instanceof Error ? error.message : String(error));
        return false;
      }

      setLanggraphThreadId(null);
      persistence.clearAll();
      setStatusNote(
        "This conversation was linked to an invalid LangGraph thread. Send a new message to create a fresh backend session.",
      );
      return true;
    },
    [backend, persistence],
  );

  const streamCallbacks = useMemo(
    () => ({
      onThreadId(nextThreadId: string) {
        setLanggraphThreadId(nextThreadId);
        persistence.setThreadId(nextThreadId);

        const activeThreadId = selectedThreadIdRef.current;
        if (activeThreadId) {
          void backend
            .attachLangGraphThread(activeThreadId, nextThreadId)
            .catch((error) => {
              setStatusNote(error instanceof Error ? error.message : String(error));
            });
        }
      },
      onCreated(run: { run_id: string }) {
        const activeThreadId = selectedThreadIdRef.current;
        if (activeThreadId) {
          void backend
            .setRunning(activeThreadId, run.run_id)
            .catch((error) => {
              setStatusNote(error instanceof Error ? error.message : String(error));
            });
        }
      },
      onFinish(state: unknown) {
        if (turnApi) {
          persistence.setRunId(null);
          setStatusNote("");
          return;
        }
        const activeThreadId = selectedThreadIdRef.current;
        if (activeThreadId) {
          const finalStateMessages = extractThreadMessages(state);
          const msgs =
            finalStateMessages.length > 0
              ? finalStateMessages
              : normalizeMessages(streamMessagesRef.current);

          void (async () => {
            let syncFailed = false;
            try {
              await backend.syncAssistantMessages(
                activeThreadId,
                toAssistantMirrorPayload(msgs),
              );
            } catch (error) {
              syncFailed = true;
              setStatusNote(error instanceof Error ? error.message : String(error));
            }

            try {
              await backend.setIdle(activeThreadId);
              if (!syncFailed) {
                setStatusNote("");
              }
            } catch (error) {
              setStatusNote(error instanceof Error ? error.message : String(error));
            }
          })();
        } else {
          setStatusNote("");
        }
      },
      onStop() {
        if (turnApi) {
          setStatusNote("");
          return;
        }
        const activeThreadId = selectedThreadIdRef.current;
        if (activeThreadId) {
          void backend.setIdle(activeThreadId).catch((error) => {
            setStatusNote(error instanceof Error ? error.message : String(error));
          });
        }
        setStatusNote("");
      },
      async onError(error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        if (turnApi) {
          setStatusNote(message);
          return;
        }
        const activeThreadId = selectedThreadIdRef.current;
        if (await recoverBrokenLangGraphThread(activeThreadId, message)) {
          if (activeThreadId) {
            void backend.setIdle(activeThreadId).catch((nextError) => {
              setStatusNote(
                nextError instanceof Error ? nextError.message : String(nextError),
              );
            });
          }
          return;
        }
        if (activeThreadId) {
          void backend
            .setError(activeThreadId, message)
            .catch((nextError) => {
              setStatusNote(
                nextError instanceof Error ? nextError.message : String(nextError),
              );
            });
        }
        setStatusNote(message);
      },
    }),
    [backend, persistence, recoverBrokenLangGraphThread, turnApi],
  );

  const stream = useStream(
    { authToken, threadId: langgraphThreadId },
    streamCallbacks,
  );

  // Keep stream messages ref up to date without triggering re-renders
  useEffect(() => {
    streamMessagesRef.current = stream.messages;
  }, [stream.messages]);

  const selectThread = useCallback(
    (threadId: string | null) => {
      const thread = backend.threads?.find((t) => t._id === threadId) ?? null;
      const nextLanggraphThreadId = thread?.langgraphThreadId ?? null;
      selectedThreadIdRef.current = threadId;
      setSelectedThreadId(threadId);
      setLanggraphThreadId(nextLanggraphThreadId);
      setStatusNote("");
      persistence.setRunId(null);
      if (nextLanggraphThreadId) {
        persistence.setThreadId(nextLanggraphThreadId);
      } else {
        persistence.setThreadId(null);
      }
      stream.switchThread(nextLanggraphThreadId);
    },
    [backend, persistence, stream],
  );

  const createThread = useCallback(async () => {
    const thread = await backend.createThread();
    selectThread(thread._id);
  }, [backend, selectThread]);

  const deleteThread = useCallback(
    async (threadId: string) => {
      if (threadId === selectedThreadId) {
        selectThread(null);
      }
      await backend.removeThread(threadId);
    },
    [backend, selectThread, selectedThreadId],
  );

  const submitMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) {
        return;
      }

      setSubmitInFlight(true);
      submitTimingRef.current = createSubmitTiming();

      let nextThread = backend.threads?.find((t) => t._id === selectedThreadId) ?? null;
      if (!nextThread) {
        nextThread = await backend.createThread();
        markSubmitTiming(submitTimingRef.current, "convex:createThread");
        selectThread(nextThread._id);
      }

      stream.switchThread(nextThread.langgraphThreadId ?? null);
      markSubmitTiming(submitTimingRef.current, "stream:switchThread");
      if (nextThread.langgraphThreadId) {
        persistence.setThreadId(nextThread.langgraphThreadId);
      } else {
        persistence.setThreadId(null);
      }

      setOptimisticMessages((current) => [
        ...current,
        {
          id: `local-${Date.now()}`,
          localOnly: true,
          threadId: nextThread._id,
          role: "user",
          content: trimmed,
          createdAt: Date.now(),
        },
      ]);

      setStatusNote("");

      try {
        if (turnApi) {
          const turnId = globalThis.crypto.randomUUID();
          const humanMessageId = globalThis.crypto.randomUUID();
          setActiveTurn({
            turnId,
            humanMessageId,
            threadId: nextThread._id,
            userContent: trimmed,
            turnPosition:
              Math.max(
                -1,
                ...(backend.turns ?? []).map((turn) => turn.turnPosition),
              ) + 1,
            createdAt: Date.now(),
          });
          const submitted = await turnApi.submitTurn({
            turnId,
            humanMessageId,
            uiThreadId: nextThread._id,
            content: trimmed,
          });
          setLanggraphThreadId(submitted.threadId);
          persistence.setThreadId(submitted.threadId);
          persistence.setRunId(submitted.runId);
          stream.switchThread(submitted.threadId);
          await stream.joinStream(submitted.runId);
          markSubmitTiming(submitTimingRef.current, "stream:joinedRun");
          return;
        }

        void Promise.all([
          backend.appendUserMessage(nextThread._id, trimmed),
          backend.setRunning(nextThread._id),
        ])
          .then(() => {
            markSubmitTiming(submitTimingRef.current, "convex:persistUserAndRunState");
          })
          .catch((error) => {
            setStatusNote(error instanceof Error ? error.message : String(error));
          });

        await stream.submit(
          { messages: [{ type: "human", content: trimmed }] },
          { streamResumable: true, onDisconnect: "continue" },
        );
        markSubmitTiming(submitTimingRef.current, "stream:submitReturned");
      } finally {
        setSubmitInFlight(false);
      }
    },
    [backend, persistence, selectedThreadId, selectThread, stream, turnApi],
  );

  const stop = useCallback(async () => {
    const threadId = persistence.getThreadId();
    const runId = persistence.getRunId();
    if (turnApi && threadId && runId) {
      await turnApi.cancelRun(threadId, runId);
    }
    await stream.stop();
    persistence.setRunId(null);
  }, [persistence, stream, turnApi]);

  // Auto-deselect deleted threads
  useEffect(() => {
    if (!selectedThreadId) {
      return;
    }
    const exists = backend.threads?.some((thread) => thread._id === selectedThreadId);
    if (!exists) {
      selectThread(null);
    }
  }, [selectedThreadId, selectThread, backend.threads]);

  // Handle interrupts
  useEffect(() => {
    const interruptCount = stream.interrupts.length;
    if (interruptCount === 0) {
      handledInterruptCountRef.current = 0;
      return;
    }
    if (interruptCount !== handledInterruptCountRef.current) {
      handledInterruptCountRef.current = interruptCount;
      setStatusNote("Chat session hit an unexpected pause — started a fresh conversation.");
      setSelectedThreadId(null);
      setLanggraphThreadId(null);
      persistence.clearAll();
      stream.switchThread(null);
    }
  }, [stream.interrupts.length, persistence, stream]);

  const normalizedStreamMessages = useMemo(
    () => normalizeMessages(stream.messages),
    [stream.messages],
  );

  const liveAssistantMessage = useMemo(() => {
    if (!stream.isLoading) {
      return null;
    }
    return selectLiveAssistantMessage(backend.messages ?? [], normalizedStreamMessages);
  }, [backend.messages, stream.isLoading, normalizedStreamMessages]);

  const liveAssistantMessages = useMemo(() => {
    const persisted = (backend.turns ?? []).flatMap((turn) =>
      turn.assistantMessages.map((message) => ({
        id: message.id,
        langgraphMessageId: message.langgraphMessageId,
        role: "assistant" as const,
        content: `${message.canonicalContent}${message.displayOnlyContent ?? ""}`,
        createdAt: message.createdAt,
        messagePosition: message.messagePosition,
      })),
    );
    return selectLiveAssistantMessages(persisted, normalizedStreamMessages);
  }, [backend.turns, normalizedStreamMessages]);

  useEffect(() => {
    if (!activeTurn) {
      return;
    }
    const persisted = (backend.turns ?? []).find(
      (turn) => turn.turnId === activeTurn.turnId,
    );
    if (
      persisted &&
      (persisted.status === "completed" ||
        persisted.status === "failed" ||
        persisted.status === "cancelled")
    ) {
      setActiveTurn(null);
    }
  }, [activeTurn, backend.turns]);

  const showThinking =
    stream.isLoading &&
    !liveAssistantMessage &&
    ((backend.messages?.length ?? 0) > 0 ||
      optimisticMessages.some((message) => message.threadId === selectedThreadId));

  useEffect(() => {
    const timing = submitTimingRef.current;
    if (!stream.isLoading || !timing || timing.firstChunkLogged || !liveAssistantMessage) {
      return;
    }
    timing.firstChunkLogged = true;
    logSubmitTiming(timing, "stream:firstAssistantChunk");
  }, [liveAssistantMessage, stream.isLoading]);

  useEffect(() => {
    const persisted = backend.messages ?? [];
    if (optimisticMessages.length === 0 || persisted.length === 0) {
      return;
    }
    setOptimisticMessages((current) => {
      const next = current.filter(
        (message) => !hasPersistedEquivalent(persisted, message),
      );
      return next.length === current.length ? current : next;
    });
  }, [backend.messages, optimisticMessages.length]);

  const displayMessages = useMemo(() => {
    const persisted = backend.messages ?? [];
    const activeThreadOptimistic = optimisticMessages.filter(
      (message) =>
        message.threadId === selectedThreadId &&
        !hasPersistedEquivalent(persisted, message),
    );
    if (!liveAssistantMessage) {
      return orderTranscriptMessages([...persisted, ...activeThreadOptimistic]);
    }
    return orderTranscriptMessages([
      ...persisted,
      ...activeThreadOptimistic,
      liveAssistantMessage,
    ]);
  }, [backend.messages, liveAssistantMessage, optimisticMessages, selectedThreadId]);

  const displayTurns = useMemo(() => {
    const turns = [...(backend.turns ?? [])].sort(
      (left, right) => left.turnPosition - right.turnPosition,
    );
    if (!activeTurn || activeTurn.threadId !== selectedThreadId) {
      return turns;
    }

    const liveMessages = liveAssistantMessages.map((message, index) => ({
      id:
        message.id ??
        message.langgraphMessageId ??
        `${activeTurn.turnId}-assistant-${index}`,
      langgraphMessageId: message.langgraphMessageId ?? message.id,
      messagePosition: message.messagePosition ?? index,
      canonicalContent: message.content,
      createdAt: message.createdAt,
    }));
    const existingIndex = turns.findIndex(
      (turn) => turn.turnId === activeTurn.turnId,
    );
    if (existingIndex === -1) {
      return [
        ...turns,
        {
          turnId: activeTurn.turnId,
          turnPosition: activeTurn.turnPosition,
          userContent: activeTurn.userContent,
          status: stream.isLoading ? "running" : "pending",
          assistantMessages: liveMessages,
          createdAt: activeTurn.createdAt,
        } satisfies ConversationTurn,
      ];
    }

    const existing = turns[existingIndex];
    const messagesById = new Map(
      existing.assistantMessages.map((message) => [message.id, message]),
    );
    for (const message of liveMessages) {
      messagesById.set(message.id, {
        ...messagesById.get(message.id),
        ...message,
      });
    }
    turns[existingIndex] = {
      ...existing,
      assistantMessages: [...messagesById.values()].sort(
        (left, right) => left.messagePosition - right.messagePosition,
      ),
    };
    return turns;
  }, [
    activeTurn,
    backend.turns,
    liveAssistantMessages,
    selectedThreadId,
    stream.isLoading,
  ]);

  const busy = submitInFlight || stream.isLoading || backend.runState?.status === "running";
  const isInterrupted = backend.runState?.status === "interrupted";

  const selectedThread = useMemo(
    () => backend.threads?.find((thread) => thread._id === selectedThreadId) ?? null,
    [backend.threads, selectedThreadId],
  );

  return {
    viewer: backend.viewer ?? null,
    threads: backend.threads ?? [],
    selectedThread,
    messages: displayMessages,
    turns: displayTurns,
    runState: backend.runState ?? null,
    isStreaming: stream.isLoading,
    showThinking,
    busy,
    statusNote: statusNote || null,
    streamError: stream.error,
    isInterrupted,
    selectThread,
    createThread,
    deleteThread,
    submitMessage,
    stop,
  };
}
