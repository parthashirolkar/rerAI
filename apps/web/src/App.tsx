import { startTransition, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useStream } from "@langchain/react";
import {
  Plus,
  PanelLeftClose,
  PanelLeft,
  FileText,
  MessageSquare,
  Loader2,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Composer } from "./components/Composer";
import { InterruptDialog } from "./components/InterruptDialog";
import { ReportPanel } from "./components/ReportPanel";
import { Transcript } from "./components/Transcript";
import {
  API_URL,
  ASSISTANT_ID,
  clearPersistedRunId,
  clearPersistedThreadId,
  getPersistedRunId,
  getPersistedThreadId,
  persistRunId,
  persistThreadId,
} from "./lib/langgraphClient";
import { extractMessageText, isAssistantMessage, isUserMessage } from "./lib/messages";
import { deriveProgressState, parsePermitReport } from "./lib/report";

const SAMPLE_QUERIES = [
  "Assess permit feasibility for a 2,000 sq m plot near Hinjewadi Phase 2, Pune.",
  "Check development potential for Survey No. 45/2, Baner, Pune.",
  "Analyze this site for setbacks, FSI, and transit access: 18.559, 73.786.",
];

const THREAD_HISTORY_KEY = "rerai.thread-history";

type ThreadMeta = {
  id: string;
  title: string;
  updatedAt: number;
};

function loadThreadHistory(): ThreadMeta[] {
  try {
    const raw = localStorage.getItem(THREAD_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveThreadHistory(threads: ThreadMeta[]) {
  localStorage.setItem(THREAD_HISTORY_KEY, JSON.stringify(threads));
}

export default function App() {
  const [draft, setDraft] = useState("");
  const [threadId, setThreadId] = useState<string | null>(() => getPersistedThreadId());
  const [activeRunId, setActiveRunId] = useState<string | null>(() => getPersistedRunId());
  const [statusNote, setStatusNote] = useState<string>("");
  const [lastSubmittedAt, setLastSubmittedAt] = useState<number | null>(null);
  const [progressTick, setProgressTick] = useState(0);
  const [showReport, setShowReport] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [threadHistory, setThreadHistory] = useState<ThreadMeta[]>(() => loadThreadHistory());

  const SIDEBAR_MIN = 200;
  const SIDEBAR_MAX = 400;
  const SIDEBAR_DEFAULT = 256;
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT);
  const isResizing = useRef(false);
  const sidebarRef = useRef<HTMLDivElement>(null);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    const startX = e.clientX;
    const startWidth = sidebarWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    const onMove = (ev: MouseEvent) => {
      if (!isResizing.current) return;
      const delta = ev.clientX - startX;
      const next = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startWidth + delta));
      setSidebarWidth(next);
    };
    const onUp = () => {
      isResizing.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [sidebarWidth]);

  const stream = useStream<Record<string, unknown>>({
    apiUrl: API_URL,
    assistantId: ASSISTANT_ID,
    threadId,
    fetchStateHistory: true,
    reconnectOnMount: true,
    onThreadId(nextThreadId) {
      setThreadId(nextThreadId);
      persistThreadId(nextThreadId);
    },
    onCreated(run) {
      setActiveRunId(run.run_id);
      persistRunId(run.run_id);
    },
    onFinish() {
      setActiveRunId(null);
      clearPersistedRunId();
      setStatusNote("");
    },
    onStop() {
      setActiveRunId(null);
      clearPersistedRunId();
      setStatusNote("");
    },
    onError(error) {
      setStatusNote(error instanceof Error ? error.message : String(error));
    },
  });

  useEffect(() => {
    if (threadId) {
      persistThreadId(threadId);
    }
  }, [threadId]);

  useEffect(() => {
    if (!stream.isLoading) return;
    const timer = window.setInterval(() => setProgressTick((v) => v + 1), 4_000);
    return () => window.clearInterval(timer);
  }, [stream.isLoading]);

  const messages = useMemo(
    () => stream.messages.filter((m) => isUserMessage(m) || isAssistantMessage(m)),
    [stream.messages],
  );

  const latestAssistantMarkdown = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (isAssistantMessage(messages[i])) return extractMessageText(messages[i]);
    }
    return "";
  }, [messages]);

  const deferredAssistantMarkdown = useDeferredValue(latestAssistantMarkdown);
  const report = useMemo(() => parsePermitReport(deferredAssistantMarkdown), [deferredAssistantMarkdown]);
  const progress = useMemo(
    () => deriveProgressState(stream.isLoading, lastSubmittedAt, activeRunId),
    [activeRunId, lastSubmittedAt, progressTick, stream.isLoading],
  );

  const hasReport = Boolean(report.summary || report.sections.length > 0);
  const interrupts = stream.interrupts as { id?: string; value?: unknown; when?: string }[];

  useEffect(() => {
    if (messages.length > 0 && threadId) {
      const firstUserMsg = messages.find(isUserMessage);
      const title = firstUserMsg
        ? extractMessageText(firstUserMsg).slice(0, 60)
        : "New chat";
      setThreadHistory((prev) => {
        const existing = prev.findIndex((t) => t.id === threadId);
        const updated: ThreadMeta[] =
          existing >= 0
            ? prev.map((t, i) =>
                i === existing ? { ...t, title, updatedAt: Date.now() } : t,
              )
            : [{ id: threadId, title, updatedAt: Date.now() }, ...prev];
        saveThreadHistory(updated);
        return updated;
      });
    }
  }, [messages.length, threadId]);

  const onSubmit = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    setDraft("");
    setLastSubmittedAt(Date.now());
    await stream.submit(
      { messages: [{ type: "human", content: trimmed }] },
      { streamResumable: true, onDisconnect: "continue" },
    );
  };

  const onNewThread = () => {
    stream.switchThread(null);
    setThreadId(null);
    setActiveRunId(null);
    setLastSubmittedAt(null);
    setStatusNote("");
    setShowReport(false);
    clearPersistedThreadId();
    clearPersistedRunId();
    setMobileSidebarOpen(false);
  };

  const onSwitchThread = (id: string) => {
    stream.switchThread(id);
    setThreadId(id);
    setActiveRunId(null);
    setLastSubmittedAt(null);
    setStatusNote("");
    setShowReport(false);
    persistThreadId(id);
    clearPersistedRunId();
    setMobileSidebarOpen(false);
  };

  const onDeleteThread = (id: string) => {
    setThreadHistory((prev) => {
      const updated = prev.filter((t) => t.id !== id);
      saveThreadHistory(updated);
      return updated;
    });
    if (id === threadId) {
      onNewThread();
    }
  };

  const onResumeInterrupt = async (resumeValue: unknown) => {
    await stream.submit(null, {
      command: { resume: resumeValue },
      multitaskStrategy: "interrupt",
    });
  };

  const sortedHistory = useMemo(
    () => [...threadHistory].sort((a, b) => b.updatedAt - a.updatedAt),
    [threadHistory],
  );

  const sidebarContent = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between p-4 pb-2">
        <h2 className="text-sm font-semibold">Chats</h2>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-xs" onClick={onNewThread}>
              <Plus className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>New chat</TooltipContent>
        </Tooltip>
      </div>
      <Separator />
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-0.5 p-2">
          {sortedHistory.length === 0 ? (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              No conversations yet
            </p>
          ) : (
            sortedHistory.map((t) => (
              <div
                key={t.id}
                className={`group flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors cursor-pointer ${
                  t.id === threadId
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                }`}
                onClick={() => onSwitchThread(t.id)}
              >
                <MessageSquare className="size-3.5 shrink-0" />
                <span className="flex-1 truncate">{t.title}</span>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteThread(t.id);
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

  return (
    <TooltipProvider>
      <div className="flex h-full">
        <InterruptDialog
          busy={stream.isLoading}
          interrupts={interrupts}
          onResume={onResumeInterrupt}
        />
        {/* Desktop sidebar */}
        <div
          ref={sidebarRef}
          className={`hidden md:flex relative flex-col border-r bg-sidebar ${
            sidebarOpen ? "" : "w-0 overflow-hidden"
          }`}
          style={sidebarOpen ? { width: sidebarWidth } : undefined}
        >
          {sidebarContent}
          {sidebarOpen && (
            <div
              onMouseDown={handleResizeStart}
              className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-ring/15 active:bg-ring/25 transition-colors z-10"
            />
          )}
        </div>

        {/* Mobile sidebar */}
        <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
          <SheetContent side="left" className="w-72 p-0">
            <SheetTitle className="sr-only">Chat history</SheetTitle>
            {sidebarContent}
          </SheetContent>
        </Sheet>

        {/* Main area */}
        <div className="flex flex-1 flex-col min-w-0">
          {/* Header */}
          <header className="flex items-center justify-between border-b px-3 py-2">
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => {
                      if (window.innerWidth < 768) {
                        setMobileSidebarOpen(true);
                      } else {
                        setSidebarOpen((v) => !v);
                      }
                    }}
                  >
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

              {stream.isLoading && (
                <Badge variant="secondary" className="gap-1.5 text-[10px]">
                  <Loader2 className="size-3 animate-spin" />
                  Thinking
                </Badge>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              {hasReport && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={showReport ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => setShowReport((v) => !v)}
                    >
                      <FileText className="size-3.5" />
                      <span className="hidden sm:inline">Report</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Toggle report panel</TooltipContent>
                </Tooltip>
              )}


            </div>
          </header>

          {/* Content area */}
          <div className="relative flex min-h-0 flex-1">
            <div
              className={`flex flex-1 flex-col ${
                showReport ? "border-r" : ""
              }`}
            >
              <Transcript
                hasMessages={messages.length > 0}
                isStreaming={stream.isLoading}
                messages={messages}
                progressDetail={progress.detail}
                sampleQueries={SAMPLE_QUERIES}
                onUseSample={(sample) =>
                  startTransition(() => setDraft(sample))
                }
              />
              <Composer
                busy={stream.isLoading}
                draft={draft}
                onChange={setDraft}
                onSubmit={onSubmit}
              />
            </div>

            {showReport && (
              <div className="hidden w-[380px] flex-shrink-0 overflow-y-auto lg:block">
                <ReportPanel error={stream.error} report={report} />
              </div>
            )}
          </div>

          {/* Status bar */}
          {statusNote && (
            <div className="border-t bg-destructive/5 px-4 py-2">
              <p className="text-xs text-destructive">{statusNote}</p>
            </div>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}
