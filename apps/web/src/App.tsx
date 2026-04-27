import { startTransition, useState } from "react";
import {
  Authenticated,
  AuthLoading,
  Unauthenticated,
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
import { ErrorBoundary } from "@/components/ErrorBoundary";
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
import { ReportPanel } from "./components/ReportPanel";
import { Transcript } from "./components/Transcript";
import {
  clearPersistedRunId,
  clearPersistedThreadId,
} from "./lib/langgraphClient";
import { useChatSession } from "./hooks/useChatSession";

const SAMPLE_QUERIES = [
  "Assess permit feasibility for a 2,000 sq m plot near Hinjewadi Phase 2, Pune.",
  "Check development potential for Survey No. 45/2, Baner, Pune.",
  "Analyze this site for setbacks, FSI, and transit access: 18.559, 73.786.",
];

export default function App() {
  const [resetKey, setResetKey] = useState(0);

  return (
    <>
      <AuthLoading>
        <LoadingScreen />
      </AuthLoading>
      <Unauthenticated>
        <AuthScreen />
      </Unauthenticated>
      <Authenticated>
        <ErrorBoundary
          onReset={() => {
            clearPersistedThreadId();
            clearPersistedRunId();
            setResetKey((k) => k + 1);
          }}
        >
          <AuthenticatedApp key={resetKey} />
        </ErrorBoundary>
      </Authenticated>
    </>
  );
}

function AuthenticatedApp() {
  const session = useChatSession();

  const sidebarContent = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between p-4 pb-2">
        <h2 className="text-sm font-semibold">Chats</h2>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-xs" onClick={() => session.selectThread(null)}>
              <Plus className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>New chat</TooltipContent>
        </Tooltip>
      </div>
      <Separator />
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-0.5 p-2">
          {session.threads.length === 0 ? (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              No conversations yet
            </p>
          ) : (
            session.threads.map((thread) => (
              <div
                key={thread._id}
                className={`group flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                  thread._id === session.selectedThreadId
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                }`}
                onClick={() => session.selectThread(thread)}
              >
                <span className="relative size-3.5 shrink-0">
                  <MessageSquare className="absolute inset-0 size-3.5 transition-opacity group-hover:opacity-0 group-focus-within:opacity-0" />
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    className="absolute -inset-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
                    onClick={(event) => {
                      event.stopPropagation();
                      void session.deleteThread(thread._id);
                    }}
                    aria-label="Delete conversation"
                  >
                    <X className="size-3" />
                  </Button>
                </span>
                <span className="flex-1 truncate">{thread.title}</span>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );

  if (!session.isReady) {
    return <LoadingScreen />;
  }

  return (
    <TooltipProvider>
      <div className="flex h-dvh overflow-hidden">
        <div
          className={`relative hidden flex-col border-r bg-sidebar-accent md:flex ${
            session.sidebarOpen ? "" : "w-0 overflow-hidden"
          }`}
          style={session.sidebarOpen ? { width: session.sidebarWidth } : undefined}
        >
          {sidebarContent}
          {session.sidebarOpen ? (
            <div
              onMouseDown={session.startSidebarResize}
              className="absolute top-0 right-0 bottom-0 z-10 w-1.5 cursor-col-resize transition-colors hover:bg-ring/15 active:bg-ring/25"
            />
          ) : null}
        </div>

        <Sheet open={session.mobileSidebarOpen} onOpenChange={session.setMobileSidebarOpen}>
          <SheetContent side="left" className="w-72 p-0">
            <SheetTitle className="sr-only">Chat history</SheetTitle>
            {sidebarContent}
          </SheetContent>
        </Sheet>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <header className="flex items-center justify-between border-b px-3 py-2">
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon-sm" onClick={session.toggleSidebar}>
                    {session.sidebarOpen ? (
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

              {session.busy ? (
                <Badge variant="secondary" className="gap-1.5 text-[10px]">
                  <Loader2 className="size-3 animate-spin" />
                  {session.isInterrupted ? "Review Required" : "Thinking"}
                </Badge>
              ) : null}
            </div>

            <div className="flex items-center gap-1.5">
              {session.hasReport ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={session.showReport ? "secondary" : "ghost"}
                      size="sm"
                      onClick={session.toggleReport}
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
                      session.signOut();
                    }}
                  >
                    <LogOut className="size-3.5" />
                    <span className="hidden sm:inline">
                      {session.viewer?.name ?? session.viewer?.email ?? "Sign out"}
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Sign out</TooltipContent>
              </Tooltip>
            </div>
          </header>

          <div className="relative flex min-h-0 flex-1 overflow-hidden">
            <div className={`flex min-h-0 flex-1 flex-col overflow-hidden ${session.showReport ? "border-r" : ""}`}>
              <Transcript
                hasMessages={session.messages.length > 0}
                isStreaming={session.isStreaming}
                showThinking={session.showThinking}
                messages={session.messages}
                sampleQueries={SAMPLE_QUERIES}
                onUseSample={(sample) => startTransition(() => session.setDraft(sample))}
              />
              <Composer
                busy={session.busy}
                draft={session.draft}
                onChange={session.setDraft}
                onSubmit={session.submitMessage}
              />
            </div>

            {session.showReport ? (
              <div className="hidden w-[380px] flex-shrink-0 overflow-y-auto lg:block">
                <ReportPanel error={session.streamError} report={session.report} />
              </div>
            ) : null}
          </div>

          {session.statusNote ? (
            <div className="border-t bg-destructive/5 px-4 py-2">
              <p className="text-xs text-destructive">{session.statusNote}</p>
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
