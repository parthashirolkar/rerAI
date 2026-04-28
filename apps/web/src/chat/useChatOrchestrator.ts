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
  toAssistantMirrorPayload,
} from "@/lib/messages";
import type {
  UseChatOrchestratorOptions,
  ChatOrchestratorState,
  ChatOrchestratorActions,
} from "./ports";

export function useChatOrchestrator({
  backend,
  persistence,
  useStream,
  authToken,
}: UseChatOrchestratorOptions): ChatOrchestratorState & ChatOrchestratorActions {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [langgraphThreadId, setLanggraphThreadId] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState("");

  const selectedThreadIdRef = useRef<string | null>(selectedThreadId);
  const streamMessagesRef = useRef<unknown[]>([]);

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
    [backend, persistence, recoverBrokenLangGraphThread],
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

      let nextThread = backend.threads?.find((t) => t._id === selectedThreadId) ?? null;
      if (!nextThread) {
        nextThread = await backend.createThread();
        selectThread(nextThread._id);
      }

      stream.switchThread(nextThread.langgraphThreadId ?? null);
      if (nextThread.langgraphThreadId) {
        persistence.setThreadId(nextThread.langgraphThreadId);
      } else {
        persistence.setThreadId(null);
      }

      await backend.appendUserMessage(nextThread._id, trimmed);
      await backend.setRunning(nextThread._id);

      setStatusNote("");

      await stream.submit(
        { messages: [{ type: "human", content: trimmed }] },
        { streamResumable: true, onDisconnect: "continue" },
      );
    },
    [backend, persistence, selectedThreadId, selectThread, stream],
  );

  const stop = useCallback(() => {
    stream.stop();
  }, [stream]);

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
    if (stream.interrupts.length > 0) {
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

  const showThinking =
    stream.isLoading && !liveAssistantMessage && (backend.messages?.length ?? 0) > 0;

  const displayMessages = useMemo(() => {
    const persisted = backend.messages ?? [];
    if (!liveAssistantMessage) {
      return persisted;
    }
    return [...persisted, liveAssistantMessage];
  }, [backend.messages, liveAssistantMessage]);

  const busy = stream.isLoading || backend.runState?.status === "running";
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
    runState: backend.runState ?? null,
    isStreaming: stream.isLoading,
    showThinking,
    busy,
    statusNote: statusNote || null,
    streamError: stream.error,
    isInterrupted,
    hasReport: false,
    selectThread,
    createThread,
    deleteThread,
    submitMessage,
    stop,
  };
}
