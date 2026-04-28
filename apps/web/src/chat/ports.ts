import type { Id } from "@convex-generated/dataModel";
import type { ChatMessage, AssistantMirrorPayload } from "@/lib/messages";

export type Viewer = {
  name?: string;
  email?: string;
  _id?: Id<"users">;
};

export type Thread = {
  _id: Id<"uiThreads">;
  title: string;
  langgraphThreadId?: string;
  updatedAt: number;
  userId?: Id<"users">;
};

export type RunState = {
  status: "idle" | "running" | "error" | "interrupted";
  langgraphRunId?: string;
  errorMessage?: string;
};

export interface BackendPort {
  viewer: Viewer | null | undefined;
  threads: Thread[] | undefined;
  runState: RunState | null | undefined;
  messages: ChatMessage[] | undefined;

  setActiveThread(threadId: string | null): void;
  ensureViewer(): Promise<void>;
  createThread(): Promise<Thread>;
  removeThread(threadId: string): Promise<void>;
  attachLangGraphThread(threadId: string, langgraphThreadId: string): Promise<void>;
  detachLangGraphThread(threadId: string): Promise<void>;
  appendUserMessage(threadId: string, content: string): Promise<void>;
  syncAssistantMessages(threadId: string, messages: AssistantMirrorPayload[]): Promise<void>;
  setRunning(threadId: string, langgraphRunId?: string): Promise<void>;
  setError(threadId: string, errorMessage: string): Promise<void>;
  setIdle(threadId: string): Promise<void>;
}

export interface StreamState {
  messages: unknown[];
  isLoading: boolean;
  error: Error | null;
  interrupts: unknown[];
  switchThread(threadId: string | null): void;
  submit(
    payload: { messages: Array<{ type: string; content: string }> },
    options: { streamResumable: boolean; onDisconnect: "continue" },
  ): Promise<void>;
  stop(): void;
}

export interface StreamCallbacks {
  onThreadId?(threadId: string): void;
  onCreated?(run: { run_id: string }): void;
  onFinish?(state: unknown): void;
  onStop?(): void;
  onError?(error: unknown): void;
}

export type UseStreamAdapter = (
  config: { authToken: string | null; threadId: string | null },
  callbacks: StreamCallbacks,
) => StreamState;

export interface PersistencePort {
  getThreadId(): string | null;
  setThreadId(id: string | null): void;
  getRunId(): string | null;
  setRunId(id: string | null): void;
  clearAll(): void;
}

export interface UseChatOrchestratorOptions {
  backend: BackendPort;
  persistence: PersistencePort;
  useStream: UseStreamAdapter;
  authToken: string | null;
}

export interface ChatOrchestratorState {
  viewer: Viewer | null;
  threads: Thread[];
  selectedThread: Thread | null;
  messages: ChatMessage[];
  runState: RunState | null;
  isStreaming: boolean;
  showThinking: boolean;
  busy: boolean;
  statusNote: string | null;
  streamError: Error | null;
  isInterrupted: boolean;
  hasReport: boolean;
}

export interface ChatOrchestratorActions {
  selectThread(threadId: string | null): void;
  createThread(): Promise<void>;
  deleteThread(threadId: string): Promise<void>;
  submitMessage(content: string): Promise<void>;
  stop(): void;
}
