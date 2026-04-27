import React, {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useStream } from "@langchain/react";
import { useAuthActions, useAuthToken } from "@convex-dev/auth/react";
import type { Id } from "@convex-generated/dataModel";
import {
  useConvexAuth,
  useMutation,
  usePaginatedQuery,
  useQuery,
} from "convex/react";
import { api } from "@/lib/convexApi";
import {
  ASSISTANT_ID,
  clearPersistedRunId,
  clearPersistedThreadId,
  createLangGraphClient,
  persistRunId,
  persistThreadId,
} from "@/lib/langgraphClient";
import {
  extractThreadStateMessages,
  extractMessageText,
  getMessageTimestamp,
  isAssistantMessage,
  isUserMessage,
} from "@/lib/messages";
import { parsePermitReport, type ParsedPermitReport } from "@/lib/report";

const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 400;
const SIDEBAR_DEFAULT = 256;

export type ChatThread = {
  _id: Id<"uiThreads">;
  title: string;
  langgraphThreadId?: string;
  updatedAt: number;
  userId?: Id<"users">;
};

export type ChatMessage = {
  _id?: Id<"uiMessages">;
  id?: string;
  role: string;
  content: string;
  createdAt: number;
};

export type ChatSession = {
  isReady: boolean;
  viewer: { name?: string; email?: string; _id?: Id<"users"> } | null;
  signOut: () => void;

  threads: ChatThread[];
  selectedThreadId: Id<"uiThreads"> | null;

  messages: ChatMessage[];
  isStreaming: boolean;
  showThinking: boolean;

  draft: string;
  setDraft: (draft: string) => void;
  submitMessage: (content: string) => Promise<void>;
  busy: boolean;

  report: ParsedPermitReport;
  hasReport: boolean;
  showReport: boolean;
  toggleReport: () => void;

  statusNote: string;
  streamError: unknown;
  isInterrupted: boolean;

  sidebarOpen: boolean;
  toggleSidebar: () => void;
  sidebarWidth: number;
  startSidebarResize: (event: React.MouseEvent) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;

  selectThread: (thread: ChatThread | null) => void;
  deleteThread: (threadId: Id<"uiThreads">) => Promise<void>;
};

function sortMessagesAscending(messages: ChatMessage[]) {
  return [...messages].sort((left, right) => left.createdAt - right.createdAt);
}

function getAssistantMirrorPayload(messages: unknown[]) {
  return messages
    .filter(isAssistantMessage)
    .map((message, index) => ({
      langgraphMessageId:
        message && typeof message === "object" && "id" in message
          ? String((message as { id?: string }).id ?? "")
          : undefined,
      content: extractMessageText(message),
      createdAt: getMessageTimestamp(message) ?? Date.now() + index,
    }))
    .filter((message) => message.content.trim().length > 0)
    .map((message) => ({
      ...message,
      langgraphMessageId: message.langgraphMessageId || undefined,
    }));
}
export function useChatSession(): ChatSession {
  const { signOut } = useAuthActions();
  const authToken = useAuthToken();
  const { isAuthenticated } = useConvexAuth();

  const ensureViewer = useMutation(api.users.ensureViewer);
  const createThread = useMutation(api.threads.create);
  const removeThread = useMutation(api.threads.remove);
  const attachLangGraphThread = useMutation(api.threads.attachLangGraphThread);
  const detachLangGraphThread = useMutation(api.threads.detachLangGraphThread);
  const appendUserMessage = useMutation(api.messages.appendUserMessage);
  const syncAssistantMessages = useMutation(api.messages.syncAssistantMessages);
  const updatePreferences = useMutation(api.preferences.updateMine);
  const setRunning = useMutation(api.runState.setRunning);
  const setError = useMutation(api.runState.setError);
  const setIdle = useMutation(api.runState.setIdle);

  const [viewerReady, setViewerReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [threadsHydrated, setThreadsHydrated] = useState(false);
  const [selectedThreadId, setSelectedThreadId] = useState<Id<"uiThreads"> | null>(null);
  const [langgraphThreadId, setLanggraphThreadId] = useState<string | null>(null);
  const [, setActiveRunId] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState("");
  const [showReport, setShowReport] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT);

  const selectedThreadIdRef = useRef<Id<"uiThreads"> | null>(selectedThreadId);
  const streamMessagesRef = useRef<unknown[]>([]);
  const hydratedPreferencesRef = useRef(false);
  const isResizing = useRef(false);

  useEffect(() => {
    selectedThreadIdRef.current = selectedThreadId;
  }, [selectedThreadId]);

  useEffect(() => {
    if (!isAuthenticated) {
      setViewerReady(false);
      hydratedPreferencesRef.current = false;
      setThreadsHydrated(false);
      setSelectedThreadId(null);
      selectedThreadIdRef.current = null;
      setLanggraphThreadId(null);
      setActiveRunId(null);
      clearPersistedThreadId();
      clearPersistedRunId();
      return;
    }

    let cancelled = false;
    void ensureViewer({})
      .then(() => {
        if (!cancelled) {
          setViewerReady(true);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setStatusNote(error instanceof Error ? error.message : String(error));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [ensureViewer, isAuthenticated]);

  const viewer = useQuery(api.users.getCurrent, viewerReady ? {} : "skip");
  const preferences = useQuery(api.preferences.getMine, viewerReady ? {} : "skip");
  const threadsResult = useQuery(api.threads.listMine, viewerReady ? {} : "skip");
  const threads = (threadsResult ?? []) as ChatThread[];

  const selectedThread = useMemo(
    () => threads.find((thread) => thread._id === selectedThreadId) ?? null,
    [selectedThreadId, threads],
  );
  const hydratedThread =
    threadsHydrated && viewer && selectedThread?.userId === viewer._id
      ? selectedThread
      : null;

  const runState = useQuery(
    api.runState.getForThread,
    viewerReady && hydratedThread ? { threadId: hydratedThread._id } : "skip",
  );

  const paginatedMessages = usePaginatedQuery(
    api.messages.listByThread,
    viewerReady && hydratedThread ? { threadId: hydratedThread._id } : "skip",
    { initialNumItems: 50 },
  );

  useEffect(() => {
    hydratedPreferencesRef.current = false;
    setThreadsHydrated(false);
    setSelectedThreadId(null);
    selectedThreadIdRef.current = null;
    setLanggraphThreadId(null);
    setActiveRunId(null);
    clearPersistedThreadId();
    clearPersistedRunId();
  }, [viewer?._id]);

  useEffect(() => {
    if (
      !viewerReady ||
      hydratedPreferencesRef.current ||
      !preferences ||
      threadsResult === undefined
    ) {
      return;
    }

    hydratedPreferencesRef.current = true;
    setThreadsHydrated(false);
    setSidebarWidth(preferences.sidebarWidth ?? SIDEBAR_DEFAULT);
    setSidebarOpen(preferences.sidebarOpen ?? true);
    setSelectedThreadId(null);
    selectedThreadIdRef.current = null;
    setLanggraphThreadId(null);
    setActiveRunId(null);
    clearPersistedThreadId();
    clearPersistedRunId();
    if (preferences.lastOpenedThreadId !== undefined) {
      void updatePreferences({ lastOpenedThreadId: null }).catch((error) => {
        setStatusNote(error instanceof Error ? error.message : String(error));
      });
    }
    setThreadsHydrated(true);
  }, [preferences, threads, threadsResult, updatePreferences, viewerReady]);

  const persistPreferenceSnapshot = useCallback(
    (next: {
      sidebarOpen?: boolean;
      sidebarWidth?: number;
      lastOpenedThreadId?: Id<"uiThreads"> | null;
    }) => {
      if (!viewerReady) {
        return;
      }
      void updatePreferences({
        sidebarOpen: next.sidebarOpen,
        sidebarWidth: next.sidebarWidth,
        lastOpenedThreadId:
          next.lastOpenedThreadId === undefined ? undefined : next.lastOpenedThreadId,
      }).catch((error) => {
        setStatusNote(error instanceof Error ? error.message : String(error));
      });
    },
    [updatePreferences, viewerReady],
  );

  const recoverBrokenLangGraphThread = useCallback(
    async (threadId: Id<"uiThreads"> | null, message: string) => {
      const isUnauthorizedThread =
        message.includes("Unauthorized LangGraph thread access") ||
        message.includes("Unauthorized thread access");
      if (!threadId || !isUnauthorizedThread) {
        return false;
      }

      try {
        await detachLangGraphThread({ threadId });
      } catch (error) {
        setStatusNote(error instanceof Error ? error.message : String(error));
        return false;
      }

      setLanggraphThreadId(null);
      setActiveRunId(null);
      clearPersistedThreadId();
      clearPersistedRunId();
      setStatusNote(
        "This conversation was linked to an invalid LangGraph thread. Send a new message to create a fresh backend session.",
      );
      return true;
    },
    [detachLangGraphThread],
  );
  const langgraphClient = useMemo(() => createLangGraphClient(authToken), [authToken]);

  const stream = useStream<Record<string, unknown>>({
    client: langgraphClient,
    assistantId: ASSISTANT_ID,
    threadId: langgraphThreadId,
    fetchStateHistory: true,
    reconnectOnMount: true,
    onThreadId(nextThreadId) {
      setLanggraphThreadId(nextThreadId);
      persistThreadId(nextThreadId);

      const activeThreadId = selectedThreadIdRef.current;
      if (activeThreadId) {
        void attachLangGraphThread({
          threadId: activeThreadId,
          langgraphThreadId: nextThreadId,
        }).catch((error) => {
          setStatusNote(error instanceof Error ? error.message : String(error));
        });
      }
    },
    onCreated(run) {
      setActiveRunId(run.run_id);
      persistRunId(run.run_id);

      const activeThreadId = selectedThreadIdRef.current;
      if (activeThreadId) {
        void setRunning({
          threadId: activeThreadId,
          langgraphRunId: run.run_id,
        }).catch((error) => {
          setStatusNote(error instanceof Error ? error.message : String(error));
        });
      }
    },
    onFinish(state) {
      const activeThreadId = selectedThreadIdRef.current;
      if (activeThreadId) {
        const finalStateMessages = extractThreadStateMessages(state);
        const messages =
          finalStateMessages.length > 0 ? finalStateMessages : streamMessagesRef.current;

        void (async () => {
          let syncFailed = false;
          try {
            await syncAssistantMessages({
              threadId: activeThreadId,
              messages: getAssistantMirrorPayload(messages),
            });
          } catch (error) {
            syncFailed = true;
            setStatusNote(error instanceof Error ? error.message : String(error));
          }

          try {
            await setIdle({ threadId: activeThreadId });
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

      setActiveRunId(null);
      clearPersistedRunId();
    },
    onStop() {
      const activeThreadId = selectedThreadIdRef.current;
      if (activeThreadId) {
        void setIdle({ threadId: activeThreadId }).catch((error) => {
          setStatusNote(error instanceof Error ? error.message : String(error));
        });
      }
      setActiveRunId(null);
      clearPersistedRunId();
      setStatusNote("");
    },
    async onError(error) {
      const message = error instanceof Error ? error.message : String(error);
      const activeThreadId = selectedThreadIdRef.current;
      if (await recoverBrokenLangGraphThread(activeThreadId, message)) {
        if (activeThreadId) {
          void setIdle({ threadId: activeThreadId }).catch((nextError) => {
            setStatusNote(nextError instanceof Error ? nextError.message : String(nextError));
          });
        }
        return;
      }
      if (activeThreadId) {
        void setError({
          threadId: activeThreadId,
          errorMessage: message,
        }).catch((nextError) => {
          setStatusNote(nextError instanceof Error ? nextError.message : String(nextError));
        });
      }
      setStatusNote(message);
    },
  });

  const streamMessages = useMemo(
    () =>
      stream.messages.filter((message) => isUserMessage(message) || isAssistantMessage(message)),
    [stream.messages],
  );

  useEffect(() => {
    streamMessagesRef.current = streamMessages;
  }, [streamMessages]);

  const startBlankChat = useCallback(() => {
    setSelectedThreadId(null);
    selectedThreadIdRef.current = null;
    setLanggraphThreadId(null);
    setActiveRunId(null);
    clearPersistedThreadId();
    clearPersistedRunId();
    setStatusNote("");
    stream.switchThread(null);
  }, [stream]);

  useEffect(() => {
    if (stream.interrupts.length > 0) {
      setStatusNote("Chat session hit an unexpected pause — started a fresh conversation.");
      startBlankChat();
    }
  }, [stream.interrupts.length, startBlankChat]);
  const selectThread = useCallback(
    (thread: ChatThread | null) => {
      const nextLanggraphThreadId = thread?.langgraphThreadId ?? null;
      setSelectedThreadId(thread?._id ?? null);
      selectedThreadIdRef.current = thread?._id ?? null;
      setLanggraphThreadId(nextLanggraphThreadId);
      setActiveRunId(null);
      setStatusNote("");
      setShowReport(false);
      clearPersistedRunId();
      if (nextLanggraphThreadId) {
        persistThreadId(nextLanggraphThreadId);
      } else {
        clearPersistedThreadId();
      }
      stream.switchThread(nextLanggraphThreadId);
      setMobileSidebarOpen(false);
      persistPreferenceSnapshot({ lastOpenedThreadId: thread?._id ?? null });
    },
    [persistPreferenceSnapshot, stream],
  );

  useEffect(() => {
    if (!selectedThreadId) {
      return;
    }
    const exists = threads.some((thread) => thread._id === selectedThreadId);
    if (!exists) {
      selectThread(null);
    }
  }, [selectedThreadId, selectThread, threads]);

  const persistedMessages = useMemo(() => {
    const results = (paginatedMessages.results ?? []) as ChatMessage[];
    return sortMessagesAscending(results);
  }, [paginatedMessages.results]);

  const liveAssistantMessage = useMemo(() => {
    if (!stream.isLoading) {
      return null;
    }

    for (let index = streamMessages.length - 1; index >= 0; index -= 1) {
      const message = streamMessages[index];
      if (!isAssistantMessage(message)) {
        continue;
      }
      const content = extractMessageText(message);
      if (!content.trim()) {
        continue;
      }
      return {
        id:
          message && typeof message === "object" && "id" in message
            ? String((message as { id?: string }).id ?? "streaming")
            : "streaming",
        role: "assistant",
        content,
        createdAt: getMessageTimestamp(message) ?? Date.now(),
      } satisfies ChatMessage;
    }

    return null;
  }, [stream.isLoading, streamMessages]);

  const showThinking = stream.isLoading && !liveAssistantMessage && persistedMessages.length > 0;

  const displayMessages = useMemo(() => {
    if (!liveAssistantMessage) {
      return persistedMessages;
    }
    return [...persistedMessages, liveAssistantMessage];
  }, [liveAssistantMessage, persistedMessages]);

  const latestAssistantMarkdown = useMemo(() => {
    for (let index = displayMessages.length - 1; index >= 0; index -= 1) {
      if (displayMessages[index]?.role === "assistant") {
        return displayMessages[index]?.content ?? "";
      }
    }
    return "";
  }, [displayMessages]);

  const deferredAssistantMarkdown = useDeferredValue(latestAssistantMarkdown);
  const report = useMemo(
    () => parsePermitReport(deferredAssistantMarkdown),
    [deferredAssistantMarkdown],
  );
  const hasReport = Boolean(report.summary || report.sections.length > 0);

  const startSidebarResize = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault();
      isResizing.current = true;
      const startX = event.clientX;
      const startWidth = sidebarWidth;
      let latestWidth = startWidth;

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMove = (moveEvent: MouseEvent) => {
        if (!isResizing.current) {
          return;
        }
        const delta = moveEvent.clientX - startX;
        latestWidth = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startWidth + delta));
        setSidebarWidth(latestWidth);
      };

      const onUp = () => {
        isResizing.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        persistPreferenceSnapshot({ sidebarWidth: latestWidth });
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    },
    [persistPreferenceSnapshot, sidebarWidth],
  );

  const toggleSidebar = useCallback(() => {
    if (window.innerWidth < 768) {
      setMobileSidebarOpen(true);
      return;
    }

    setSidebarOpen((value) => {
      const nextValue = !value;
      persistPreferenceSnapshot({ sidebarOpen: nextValue });
      return nextValue;
    });
  }, [persistPreferenceSnapshot]);

  const submitMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) {
        return;
      }

      let nextThread = selectedThread;
      if (!nextThread) {
        nextThread = (await createThread({})) as ChatThread | null;
        if (!nextThread) {
          return;
        }
        selectThread(nextThread);
      }

      stream.switchThread(nextThread.langgraphThreadId ?? null);
      if (nextThread.langgraphThreadId) {
        persistThreadId(nextThread.langgraphThreadId);
      } else {
        clearPersistedThreadId();
      }

      await appendUserMessage({
        threadId: nextThread._id,
        content: trimmed,
      });
      await setRunning({ threadId: nextThread._id });

      setDraft("");
      setStatusNote("");

      await stream.submit(
        { messages: [{ type: "human", content: trimmed }] },
        { streamResumable: true, onDisconnect: "continue" },
      );
    },
    [appendUserMessage, createThread, selectedThread, selectThread, setRunning, stream],
  );

  const deleteThread = useCallback(
    async (threadId: Id<"uiThreads">) => {
      await removeThread({ threadId });
      if (threadId === selectedThreadId) {
        selectThread(null);
      }
    },
    [removeThread, selectThread, selectedThreadId],
  );

  const toggleReport = useCallback(() => {
    setShowReport((value) => !value);
  }, []);

  const busy = stream.isLoading || runState?.status === "running";
  const isReady = viewerReady && !!preferences;

  return {
    isReady,
    viewer: viewer ?? null,
    signOut,
    threads,
    selectedThreadId,
    messages: displayMessages,
    isStreaming: stream.isLoading,
    showThinking,
    draft,
    setDraft,
    submitMessage,
    busy,
    report,
    hasReport,
    showReport,
    toggleReport,
    statusNote,
    streamError: stream.error,
    isInterrupted: runState?.status === "interrupted",
    sidebarOpen,
    toggleSidebar,
    sidebarWidth,
    startSidebarResize,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    selectThread,
    deleteThread,
  };
}
