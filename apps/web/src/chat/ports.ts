import type { Id } from "@convex-generated/dataModel";
import type {
  ChatMessage,
  ConversationTurn,
} from "@/lib/messages";

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
  activeTurn?: {
    status: "pending" | "running";
    langgraphThreadId?: string;
    langgraphRunId?: string;
  };
};

export interface BackendPort {
  viewer: Viewer | null | undefined;
  threads: Thread[] | undefined;
  messages: ChatMessage[] | undefined;
  turns?: ConversationTurn[] | undefined;

  setActiveThread(threadId: string | null): void;
  ensureViewer(): Promise<void>;
  createThread(): Promise<Thread>;
  removeThread(threadId: string): Promise<void>;
}

export interface StreamState {
  messages: unknown[];
  isLoading: boolean;
  error: Error | null;
  interrupts: unknown[];
  switchThread(threadId: string | null): void;
  joinStream(runId: string): Promise<void>;
  submit(
    payload: { messages: Array<{ type: string; content: string }> },
    options: { streamResumable: boolean; onDisconnect: "continue" },
  ): Promise<void>;
  stop(): void | Promise<void>;
}

export type TurnSubmission = {
  turnId: string;
  humanMessageId: string;
  uiThreadId: string;
  content: string;
};

export type SubmittedTurn = {
  turnId: string;
  humanMessageId: string;
  threadId: string;
  runId: string;
};

export interface TurnApiPort {
  submitTurn(payload: TurnSubmission): Promise<SubmittedTurn>;
  cancelRun(threadId: string, runId: string): Promise<{
    status: "completed" | "failed" | "cancelled";
  }>;
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

export interface UseChatOrchestratorOptions {
  backend: BackendPort;
  useStream: UseStreamAdapter;
  authToken: string | null;
  turnApi?: TurnApiPort;
}

export interface ChatOrchestratorState {
  viewer: Viewer | null;
  threads: Thread[];
  selectedThread: Thread | null;
  messages: ChatMessage[];
  turns: ConversationTurn[];
  isStreaming: boolean;
  isStopping: boolean;
  canStop: boolean;
  connectionStatus: "connecting" | "reconnecting" | "finalizing" | null;
  deletingThreadId: string | null;
  showThinking: boolean;
  busy: boolean;
  statusNote: string | null;
  streamError: Error | null;
  isInterrupted: boolean;
}

export interface ChatOrchestratorActions {
  selectThread(threadId: string | null): void;
  createThread(): Promise<void>;
  deleteThread(threadId: string): Promise<void>;
  submitMessage(content: string): Promise<void>;
  retryTurn(turnId: string): Promise<void>;
  stop(): Promise<void>;
  reconnect(): void;
}
