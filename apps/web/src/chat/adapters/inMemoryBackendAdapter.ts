import type { Id } from "@convex-generated/dataModel";
import type { ChatMessage } from "@/lib/messages";
import type { BackendPort, Thread, Viewer } from "../ports";

export function createInMemoryBackendAdapter(
  initial?: {
    viewer?: Viewer;
    threads?: Thread[];
    messages?: ChatMessage[];
  },
): BackendPort {
  const viewer = initial?.viewer ?? null;
  let threads = initial?.threads ?? [];
  const messages = initial?.messages ?? [];

  return {
    get viewer() {
      return viewer;
    },
    get threads() {
      return threads;
    },
    get messages() {
      return messages;
    },
    // This lightweight test adapter exposes the initialized run state/messages only.
    // It does not emulate Convex's active-thread-scoped queries.
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
  };
}
