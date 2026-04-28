import type { Id } from "@convex-generated/dataModel";
import type { ChatMessage } from "@/lib/messages";
import type { BackendPort, Thread, Viewer, RunState } from "../ports";

export function createInMemoryBackendAdapter(
  initial?: {
    viewer?: Viewer;
    threads?: Thread[];
    runState?: RunState;
    messages?: ChatMessage[];
  },
): BackendPort {
  const viewer = initial?.viewer ?? null;
  let threads = initial?.threads ?? [];
  let runState = initial?.runState ?? null;
  const messages = initial?.messages ?? [];

  return {
    get viewer() {
      return viewer;
    },
    get threads() {
      return threads;
    },
    get runState() {
      return runState;
    },
    get messages() {
      return messages;
    },
    setActiveThread() {},
    async ensureViewer() {},
    async createThread() {
      const thread: Thread = {
        _id: `thread-${threads.length + 1}` as Id<"uiThreads">,
        title: "New thread",
        updatedAt: Date.now(),
      };
      threads = [...threads, thread];
      return thread;
    },
    async removeThread(threadId) {
      threads = threads.filter((t) => t._id !== threadId);
    },
    async attachLangGraphThread() {},
    async detachLangGraphThread() {},
    async appendUserMessage() {},
    async syncAssistantMessages() {},
    async setRunning() {
      runState = { status: "running" };
    },
    async setError(_, errorMessage) {
      runState = { status: "error", errorMessage };
    },
    async setIdle() {
      runState = { status: "idle" };
    },
  };
}
