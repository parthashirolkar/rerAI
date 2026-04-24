import {
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useStream } from "@langchain/react";
import { useAuthActions, useAuthToken } from "@convex-dev/auth/react";
import {
  Authenticated,
  AuthLoading,
  Unauthenticated,
  useConvexAuth,
  useMutation,
  usePaginatedQuery,
  useQuery,
} from "convex/react";
import {
  FileText,
  Loader2,
  LogOut,
  MessageSquare,
  PanelLeft,
  PanelLeftClose,
  Plus,
  X,
} from "lucide-react";

import { AuthScreen } from "@/components/AuthScreen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Composer } from "./components/Composer";
import { InterruptDialog } from "./components/InterruptDialog";
import { ReportPanel } from "./components/ReportPanel";
import { Transcript } from "./components/Transcript";
import { api } from "./lib/convexApi";
import {
  ASSISTANT_ID,
  clearPersistedRunId,
  clearPersistedThreadId,
  createLangGraphClient,
  persistRunId,
  persistThreadId,
} from "./lib/langgraphClient";
import {
  extractThreadStateMessages,
  extractMessageText,
  getMessageTimestamp,
  isAssistantMessage,
  isUserMessage,
} from "./lib/messages";
import { deriveProgressState, parsePermitReport } from "./lib/report";

const SAMPLE_QUERIES = [
  "Assess permit feasibility for a 2,000 sq m plot near Hinjewadi Phase 2, Pune.",
  "Check development potential for Survey No. 45/2, Baner, Pune.",
  "Analyze this site for setbacks, FSI, and transit access: 18.559, 73.786.",
];

const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 400;
const SIDEBAR_DEFAULT = 256;

type ConvexThread = {
  _id: string;
  title: string;
  langgraphThreadId?: string;
  updatedAt: number;
  userId?: string;
};

type DisplayMessage = {
  _id?: string;
  id?: string;
  role: string;
  content: string;
  createdAt: number;
};

function sortMessagesAscending(messages: DisplayMessage[]) {
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

export default function App() {
  return (
    <>
      <AuthLoading>
        <LoadingScreen />
      </AuthLoading>
      <Unauthenticated>
        <AuthScreen />
      </Unauthenticated>
      <Authenticated>
        <AuthenticatedApp />
      </Authenticated>
    </>
  );
}

function AuthenticatedApp() {
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
  const setInterrupted = useMutation(api.runState.setInterrupted);
  const setError = useMutation(api.runState.setError);
  const setIdle = useMutation(api.runState.setIdle);

  const [viewerReady, setViewerReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [threadsHydrated, setThreadsHydrated] = useState(false);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [langgraphThreadId, setLanggraphThreadId] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState("");
  const [lastSubmittedAt, setLastSubmittedAt] = useState<number | null>(null);
  const [progressTick, setProgressTick] = useState(0);
  const [showReport, setShowReport] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT);

  const selectedThreadIdRef = useRef<string | null>(selectedThreadId);
  const streamMessagesRef = useRef<unknown[]>([]);
  const hydratedPreferencesRef = useRef(false);
  const isResizing = useRef(false);
  const sidebarRef = useRef<HTMLDivElement>(null);

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
      setLastSubmittedAt(null);
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
  const threads = (threadsResult ?? []) as ConvexThread[];

  const selectedThread = useMemo(
    () => threads.find((thread) => thread._id === selectedThreadId) ?? null,
    [selectedThreadId, threads],
  );
  const hydratedThread =
    threadsHydrated && viewer && selectedThread?.userId === viewer._id ? selectedThread : null;

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

    const preferredThread =
      preferences.lastOpenedThreadId === undefined
        ? null
        : (threads.find((thread) => thread._id === preferences.lastOpenedThreadId) ?? null);
    const initialThread = preferredThread ?? threads[0] ?? null;

    if (!initialThread) {
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
      return;
    }

    setSelectedThreadId(initialThread._id);
    selectedThreadIdRef.current = initialThread._id;
    setLanggraphThreadId(initialThread.langgraphThreadId ?? null);
    setActiveRunId(null);

    if (initialThread.langgraphThreadId) {
      persistThreadId(initialThread.langgraphThreadId);
    } else {
      clearPersistedThreadId();
    }

    if (preferredThread?.langgraphThreadId !== initialThread.langgraphThreadId) {
      clearPersistedRunId();
    }
    if (
      preferences.lastOpenedThreadId !== undefined &&
      preferredThread === null &&
      initialThread._id !== preferences.lastOpenedThreadId
    ) {
      void updatePreferences({ lastOpenedThreadId: initialThread._id }).catch((error) => {
        setStatusNote(error instanceof Error ? error.message : String(error));
      });
    }
    setThreadsHydrated(true);
  }, [preferences, threads, threadsResult, updatePreferences, viewerReady]);

  const persistPreferenceSnapshot = useCallback(
    (next: { sidebarOpen?: boolean; sidebarWidth?: number; lastOpenedThreadId?: string | null }) => {
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
    async (threadId: string | null, message: string) => {
      if (!threadId || !message.includes("Unauthorized LangGraph thread access")) {
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

  useEffect(() => {
    if (!stream.isLoading) {
      return;
    }
    const timer = window.setInterval(() => setProgressTick((value) => value + 1), 4_000);
    return () => window.clearInterval(timer);
  }, [stream.isLoading]);

  const streamMessages = useMemo(
    () => stream.messages.filter((message) => isUserMessage(message) || isAssistantMessage(message)),
    [stream.messages],
  );

  useEffect(() => {
    streamMessagesRef.current = streamMessages;
  }, [streamMessages]);

  useEffect(() => {
    if (stream.interrupts.length > 0 && selectedThreadId) {
      void setInterrupted({ threadId: selectedThreadId }).catch((error) => {
        setStatusNote(error instanceof Error ? error.message : String(error));
      });
    }
  }, [selectedThreadId, setInterrupted, stream.interrupts.length]);

  const selectThread = useCallback(
    (thread: ConvexThread | null) => {
      const nextLanggraphThreadId = thread?.langgraphThreadId ?? null;
      setSelectedThreadId(thread?._id ?? null);
      selectedThreadIdRef.current = thread?._id ?? null;
      setLanggraphThreadId(nextLanggraphThreadId);
      setActiveRunId(null);
      setLastSubmittedAt(null);
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
      const fallback = threads[0] ?? null;
      selectThread(fallback);
    }
  }, [selectedThreadId, selectThread, threads]);

  const persistedMessages = useMemo(() => {
    const results = (paginatedMessages.results ?? []) as DisplayMessage[];
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
      } satisfies DisplayMessage;
    }

    return null;
  }, [stream.isLoading, streamMessages]);

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
  const progress = useMemo(
    () =>
      deriveProgressState(
        stream.isLoading || runState?.status === "running",
        lastSubmittedAt,
        activeRunId,
      ),
    [activeRunId, lastSubmittedAt, progressTick, runState?.status, stream.isLoading],
  );

  const hasReport = Boolean(report.summary || report.sections.length > 0);
  const interrupts = stream.interrupts as { id?: string; value?: unknown; when?: string }[];

  const handleResizeStart = useCallback(
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

  const onNewThread = async () => {
    const created = (await createThread({})) as ConvexThread | null;
    if (!created) {
      return;
    }
    selectThread(created);
  };

  const onDeleteThread = async (threadId: string) => {
    await removeThread({ threadId });
    if (threadId === selectedThreadId) {
      stream.switchThread(null);
      setSelectedThreadId(null);
      selectedThreadIdRef.current = null;
      setLanggraphThreadId(null);
      setActiveRunId(null);
      setLastSubmittedAt(null);
      setShowReport(false);
      clearPersistedThreadId();
      clearPersistedRunId();
      persistPreferenceSnapshot({ lastOpenedThreadId: null });
    }
  };

  const onSubmit = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed) {
      return;
    }

    let nextThread = selectedThread;
    if (!nextThread) {
      nextThread = (await createThread({})) as ConvexThread | null;
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
    setLastSubmittedAt(Date.now());
    setStatusNote("");

    await stream.submit(
      { messages: [{ type: "human", content: trimmed }] },
      { streamResumable: true, onDisconnect: "continue" },
    );
  };

  const onResumeInterrupt = async (resumeValue: unknown) => {
    await stream.submit(null, {
      command: { resume: resumeValue },
      multitaskStrategy: "interrupt",
    });
  };

  const onToggleSidebar = () => {
    if (window.innerWidth < 768) {
      setMobileSidebarOpen(true);
      return;
    }

    setSidebarOpen((value) => {
      const nextValue = !value;
      persistPreferenceSnapshot({ sidebarOpen: nextValue });
      return nextValue;
    });
  };

  const busy = stream.isLoading || runState?.status === "running";

  const sidebarContent = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between p-4 pb-2">
        <h2 className="text-sm font-semibold">Chats</h2>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-xs" onClick={() => void onNewThread()}>
              <Plus className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>New chat</TooltipContent>
        </Tooltip>
      </div>
      <Separator />
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-0.5 p-2">
          {threads.length === 0 ? (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              No conversations yet
            </p>
          ) : (
            threads.map((thread) => (
              <div
                key={thread._id}
                className={`group flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                  thread._id === selectedThreadId
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                }`}
                onClick={() => selectThread(thread)}
              >
                <MessageSquare className="size-3.5 shrink-0" />
                <span className="flex-1 truncate">{thread.title}</span>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(event) => {
                    event.stopPropagation();
                    void onDeleteThread(thread._id);
                  }}
                >
                  <X className="size-3" />
                </Button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );

  if (!viewerReady || !preferences) {
    return <LoadingScreen />;
  }

  return (
    <TooltipProvider>
      <div className="flex h-full">
        <InterruptDialog
          busy={busy}
          interrupts={interrupts}
          onResume={onResumeInterrupt}
        />

        <div
          ref={sidebarRef}
          className={`relative hidden flex-col border-r bg-sidebar md:flex ${
            sidebarOpen ? "" : "w-0 overflow-hidden"
          }`}
          style={sidebarOpen ? { width: sidebarWidth } : undefined}
        >
          {sidebarContent}
          {sidebarOpen ? (
            <div
              onMouseDown={handleResizeStart}
              className="absolute top-0 right-0 bottom-0 z-10 w-1.5 cursor-col-resize transition-colors hover:bg-ring/15 active:bg-ring/25"
            />
          ) : null}
        </div>

        <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
          <SheetContent side="left" className="w-72 p-0">
            <SheetTitle className="sr-only">Chat history</SheetTitle>
            {sidebarContent}
          </SheetContent>
        </Sheet>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b px-3 py-2">
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon-sm" onClick={onToggleSidebar}>
                    {sidebarOpen ? (
                      <PanelLeftClose className="size-4" />
                    ) : (
                      <PanelLeft className="size-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Toggle sidebar</TooltipContent>
              </Tooltip>

              <span className="font-serif text-lg font-semibold tracking-tight text-ring">
                rerAI
              </span>

              {busy ? (
                <Badge variant="secondary" className="gap-1.5 text-[10px]">
                  <Loader2 className="size-3 animate-spin" />
                  {runState?.status === "interrupted" ? "Review Required" : "Thinking"}
                </Badge>
              ) : null}
            </div>

            <div className="flex items-center gap-1.5">
              {hasReport ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={showReport ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => setShowReport((value) => !value)}
                    >
                      <FileText className="size-3.5" />
                      <span className="hidden sm:inline">Report</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Toggle report panel</TooltipContent>
                </Tooltip>
              ) : null}

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      clearPersistedThreadId();
                      clearPersistedRunId();
                      void signOut();
                    }}
                  >
                    <LogOut className="size-3.5" />
                    <span className="hidden sm:inline">
                      {viewer?.name ?? viewer?.email ?? "Sign out"}
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Sign out</TooltipContent>
              </Tooltip>
            </div>
          </header>

          <div className="relative flex min-h-0 flex-1">
            <div className={`flex flex-1 flex-col ${showReport ? "border-r" : ""}`}>
              <Transcript
                hasMessages={displayMessages.length > 0}
                isStreaming={stream.isLoading}
                messages={displayMessages}
                progressDetail={progress.detail}
                sampleQueries={SAMPLE_QUERIES}
                onUseSample={(sample) => startTransition(() => setDraft(sample))}
              />
              <Composer
                busy={busy}
                draft={draft}
                onChange={setDraft}
                onSubmit={onSubmit}
              />
            </div>

            {showReport ? (
              <div className="hidden w-[380px] flex-shrink-0 overflow-y-auto lg:block">
                <ReportPanel error={stream.error} report={report} />
              </div>
            ) : null}
          </div>

          {statusNote ? (
            <div className="border-t bg-destructive/5 px-4 py-2">
              <p className="text-xs text-destructive">{statusNote}</p>
            </div>
          ) : null}
        </div>
      </div>
    </TooltipProvider>
  );
}

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="w-full max-w-xl space-y-4 rounded-3xl border bg-card p-8 shadow-sm">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}
