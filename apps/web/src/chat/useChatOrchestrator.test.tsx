import { act, renderHook, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { describe, expect, test, vi } from "vitest";

import { useChatOrchestrator } from "./useChatOrchestrator";
import type {
  BackendPort,
  PersistencePort,
  RunState,
  StreamCallbacks,
  StreamState,
  Thread,
  TurnApiPort,
  UseStreamAdapter,
  Viewer,
} from "./ports";
import type { ChatMessage } from "@/lib/messages";
import type { ConversationTurn } from "@/lib/messages";

type BackendHarness = BackendPort & {
  calls: {
    setActiveThread: ReturnType<typeof vi.fn>;
    createThread: ReturnType<typeof vi.fn>;
    removeThread: ReturnType<typeof vi.fn>;
    attachLangGraphThread: ReturnType<typeof vi.fn>;
    detachLangGraphThread: ReturnType<typeof vi.fn>;
    appendUserMessage: ReturnType<typeof vi.fn>;
    syncAssistantMessages: ReturnType<typeof vi.fn>;
    setRunning: ReturnType<typeof vi.fn>;
    setError: ReturnType<typeof vi.fn>;
    setIdle: ReturnType<typeof vi.fn>;
  };
};

function createBackendHarness(initial?: {
  viewer?: Viewer | null;
  threads?: Thread[];
  runState?: RunState | null;
  messages?: ChatMessage[];
  turns?: ConversationTurn[];
}): BackendHarness {
  let activeThreadId: string | null = null;
  let threads = initial?.threads ?? [];
  let runState = initial?.runState ?? null;
  const messages = initial?.messages ?? [];
  let turns = initial?.turns ?? [];

  const calls = {
    setActiveThread: vi.fn((threadId: string | null) => {
      activeThreadId = threadId;
    }),
    createThread: vi.fn(async () => {
      const thread = {
        _id: `thread-${threads.length + 1}`,
        title: "New thread",
        updatedAt: Date.now(),
      } as Thread;
      threads = [...threads, thread];
      return thread;
    }),
    removeThread: vi.fn(async (threadId: string) => {
      threads = threads.filter((thread) => thread._id !== threadId);
    }),
    attachLangGraphThread: vi.fn(async (threadId: string, langgraphThreadId: string) => {
      threads = threads.map((thread) =>
        thread._id === threadId ? { ...thread, langgraphThreadId } : thread,
      );
    }),
    detachLangGraphThread: vi.fn(async (threadId: string) => {
      threads = threads.map((thread) =>
        thread._id === threadId ? { ...thread, langgraphThreadId: undefined } : thread,
      );
    }),
    appendUserMessage: vi.fn(async (threadId: string, content: string) => {
      messages.push({
        _id: `msg-${messages.length + 1}`,
        role: "user",
        content,
        createdAt: Date.now(),
      });
      activeThreadId = threadId;
    }),
    syncAssistantMessages: vi.fn(async (_threadId: string, nextMessages) => {
      for (const message of nextMessages) {
        messages.push({
          _id: `msg-${messages.length + 1}`,
          role: "assistant",
          content: message.content,
          createdAt: message.createdAt,
          langgraphMessageId: message.langgraphMessageId,
        });
      }
    }),
    setRunning: vi.fn(async (_threadId: string, langgraphRunId?: string) => {
      runState = { status: "running", langgraphRunId };
    }),
    setError: vi.fn(async (_threadId: string, errorMessage: string) => {
      runState = { status: "error", errorMessage };
    }),
    setIdle: vi.fn(async () => {
      runState = { status: "idle" };
    }),
  };

  return {
    calls,
    get viewer() {
      return initial?.viewer ?? { name: "Tester" };
    },
    get threads() {
      return threads;
    },
    get runState() {
      return runState;
    },
    get messages() {
      return messages.filter((message) => !activeThreadId || message);
    },
    get turns() {
      return turns;
    },
    setActiveThread: calls.setActiveThread,
    ensureViewer: vi.fn(async () => {}),
    createThread: calls.createThread,
    removeThread: calls.removeThread,
    attachLangGraphThread: calls.attachLangGraphThread,
    detachLangGraphThread: calls.detachLangGraphThread,
    appendUserMessage: calls.appendUserMessage,
    syncAssistantMessages: calls.syncAssistantMessages,
    setRunning: calls.setRunning,
    setError: calls.setError,
    setIdle: calls.setIdle,
  };
}

function createPersistenceHarness(): PersistencePort & {
  calls: {
    setThreadId: ReturnType<typeof vi.fn>;
    setRunId: ReturnType<typeof vi.fn>;
    clearAll: ReturnType<typeof vi.fn>;
  };
} {
  let threadId: string | null = null;
  let runId: string | null = null;
  const calls = {
    setThreadId: vi.fn((id: string | null) => {
      threadId = id;
    }),
    setRunId: vi.fn((id: string | null) => {
      runId = id;
    }),
    clearAll: vi.fn(() => {
      threadId = null;
      runId = null;
    }),
  };

  return {
    calls,
    getThreadId: () => threadId,
    setThreadId: calls.setThreadId,
    getRunId: () => runId,
    setRunId: calls.setRunId,
    clearAll: calls.clearAll,
  };
}

function createTurnApiHarness(): TurnApiPort & {
  calls: {
    submitTurn: ReturnType<typeof vi.fn>;
    cancelRun: ReturnType<typeof vi.fn>;
  };
} {
  const calls = {
    submitTurn: vi.fn(async (payload) => ({
      turnId: payload.turnId,
      humanMessageId: payload.humanMessageId,
      threadId: "lg-thread-1",
      runId: "run-1",
    })),
    cancelRun: vi.fn(async () => ({ status: "cancelled" as const })),
  };
  return {
    calls,
    submitTurn: calls.submitTurn,
    cancelRun: calls.cancelRun,
  };
}

function createStreamHarness(initial?: Partial<StreamState>): {
  useStream: UseStreamAdapter;
  calls: {
    switchThread: ReturnType<typeof vi.fn>;
    joinStream: ReturnType<typeof vi.fn>;
    submit: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
  };
  setState(next: Partial<StreamState>): void;
  emitThreadId(threadId: string): void;
  emitCreated(runId: string): void;
  emitFinish(state: unknown): void;
  emitError(error: unknown): Promise<void>;
} {
  let callbacks: StreamCallbacks = {};
  let snapshot: StreamState = {
    messages: [],
    isLoading: false,
    error: null,
    interrupts: [],
    switchThread: vi.fn(),
    joinStream: vi.fn(),
    submit: vi.fn(),
    stop: vi.fn(),
    ...initial,
  };
  const listeners = new Set<() => void>();

  const publish = () => {
    for (const listener of listeners) {
      listener();
    }
  };

  const calls = {
    switchThread: vi.fn((threadId: string | null) => {
      snapshot = { ...snapshot };
      publish();
      return threadId;
    }),
    joinStream: vi.fn(async () => {}),
    submit: vi.fn(async () => {}),
    stop: vi.fn(() => {
      callbacks.onStop?.();
    }),
  };

  snapshot = {
    ...snapshot,
    switchThread: calls.switchThread,
    joinStream: calls.joinStream,
    submit: calls.submit,
    stop: calls.stop,
  };

  const useStream: UseStreamAdapter = (_config, nextCallbacks) => {
    callbacks = nextCallbacks;
    const [, forceRender] = useState(0);

    useEffect(() => {
      const listener = () => forceRender((value) => value + 1);
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    }, []);

    return snapshot;
  };

  return {
    useStream,
    calls,
    setState(next) {
      act(() => {
        snapshot = { ...snapshot, ...next };
        publish();
      });
    },
    emitThreadId(threadId) {
      act(() => {
        callbacks.onThreadId?.(threadId);
      });
    },
    emitCreated(runId) {
      act(() => {
        callbacks.onCreated?.({ run_id: runId });
      });
    },
    emitFinish(state) {
      act(() => {
        callbacks.onFinish?.(state);
      });
    },
    async emitError(error) {
      await act(async () => {
        await callbacks.onError?.(error);
      });
    },
  };
}

describe("useChatOrchestrator streaming contract", () => {
  test("submits a new conversation through the UI backend before streaming", async () => {
    const backend = createBackendHarness();
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    await act(async () => {
      await result.current.submitMessage("  Check Survey No. 45/2  ");
    });

    expect(backend.calls.createThread).toHaveBeenCalledTimes(1);
    expect(turnApi.calls.submitTurn).toHaveBeenCalledWith({
      turnId: expect.any(String),
      humanMessageId: expect.any(String),
      uiThreadId: "thread-1",
      content: "Check Survey No. 45/2",
    });
    expect(backend.calls.appendUserMessage).not.toHaveBeenCalled();
    expect(backend.calls.setRunning).not.toHaveBeenCalled();
    expect(stream.calls.submit).not.toHaveBeenCalled();
    expect(stream.calls.switchThread).toHaveBeenLastCalledWith("lg-thread-1");
    expect(stream.calls.joinStream).toHaveBeenCalledWith("run-1");

    await waitFor(() => {
      expect(result.current.selectedThread?._id).toBe("thread-1");
    });
  });

  test("attaches the LangGraph thread ID returned by the stream", async () => {
    const backend = createBackendHarness();
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    await act(async () => {
      await result.current.submitMessage("Check Baner");
    });

    stream.emitThreadId("lg-thread-1");

    await waitFor(() => {
      expect(persistence.calls.setThreadId).toHaveBeenCalledWith("lg-thread-1");
      expect(backend.calls.attachLangGraphThread).toHaveBeenCalledWith(
        "thread-1",
        "lg-thread-1",
      );
    });
  });

  test("displays only new assistant stream content while loading", async () => {
    const backend = createBackendHarness({
      messages: [
        { role: "user", content: "first", createdAt: 100 },
        {
          role: "assistant",
          content: "already persisted",
          createdAt: 200,
          id: "ai-old",
          langgraphMessageId: "ai-old",
        },
        { role: "user", content: "follow up", createdAt: 300 },
      ],
    });
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    stream.setState({
      isLoading: true,
      messages: [{ type: "ai", id: "ai-old", content: "already persisted", createdAt: 200 }],
    });

    expect(result.current.messages.map((message) => message.content)).toEqual([
      "first",
      "already persisted",
      "follow up",
    ]);

    stream.setState({
      isLoading: true,
      messages: [{ type: "ai", id: "ai-new", content: "new streamed answer", createdAt: 400 }],
    });

    expect(result.current.messages.map((message) => message.content)).toEqual([
      "first",
      "already persisted",
      "follow up",
      "new streamed answer",
    ]);
  });

  test("keeps every live Assistant Message in backend position order", async () => {
    const backend = createBackendHarness();
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    await act(async () => {
      await result.current.submitMessage("Check Baner");
    });
    stream.setState({
      isLoading: true,
      messages: [
        {
          type: "ai",
          id: "ai-progress",
          content: "Researching",
          messagePosition: 0,
        },
        {
          type: "ai",
          id: "ai-final",
          content: "Final assessment",
          messagePosition: 1,
        },
      ],
    });

    expect(
      result.current.turns[0]?.assistantMessages.map((message) => message.id),
    ).toEqual(["ai-progress", "ai-final"]);
  });

  test("merges optimistic user prompts with persisted replies in chronological order", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 300,
        } as Thread,
      ],
      messages: [
        {
          role: "assistant",
          content: "First answer",
          createdAt: Date.now() + 100_000,
        },
      ],
    });
    backend.appendUserMessage = vi.fn(async () => {});
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    await waitFor(() => {
      expect(result.current.selectedThread?._id).toBe("thread-1");
    });

    await act(async () => {
      await result.current.submitMessage("First question");
    });

    await act(async () => {
      await result.current.submitMessage("Second question");
    });

    expect(result.current.messages.map((message) => message.content)).toEqual([
      "First question",
      "Second question",
      "First answer",
    ]);
  });

  test("mirrors final assistant messages and marks the thread idle on finish", async () => {
    const backend = createBackendHarness();
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    await act(async () => {
      await result.current.submitMessage("Check Hinjewadi");
    });

    stream.emitFinish({
      values: {
        messages: [
          { type: "human", content: "Check Hinjewadi", createdAt: 100 },
          { type: "ai", id: "ai-final", content: "Final answer", createdAt: 200 },
        ],
      },
    });

    await waitFor(() => {
      expect(backend.calls.syncAssistantMessages).toHaveBeenCalledWith("thread-1", [
        { langgraphMessageId: "ai-final", content: "Final answer", createdAt: 200 },
      ]);
      expect(backend.calls.setIdle).toHaveBeenCalledWith("thread-1");
    });
  });

  test("does not finalize backend-owned turns from the browser", async () => {
    const backend = createBackendHarness();
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    await act(async () => {
      await result.current.submitMessage("Check Hinjewadi");
    });
    stream.emitFinish({
      values: {
        messages: [
          { type: "human", id: "human-1", content: "Check Hinjewadi" },
          { type: "ai", id: "ai-final", content: "Final answer" },
        ],
      },
    });

    await act(async () => {});
    expect(backend.calls.syncAssistantMessages).not.toHaveBeenCalled();
    expect(backend.calls.setIdle).not.toHaveBeenCalled();
  });

  test("marks the selected thread error with the stream error message", async () => {
    const backend = createBackendHarness();
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    await act(async () => {
      await result.current.submitMessage("Check Kothrud");
    });

    await stream.emitError(new Error("LangGraph failed"));

    await waitFor(() => {
      expect(backend.calls.setError).toHaveBeenCalledWith("thread-1", "LangGraph failed");
      expect(result.current.statusNote).toBe("LangGraph failed");
    });
  });

  test("stops the backend run before closing the local stream", async () => {
    const backend = createBackendHarness();
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    await act(async () => {
      await result.current.submitMessage("Check Kothrud");
    });
    await act(async () => {
      await result.current.stop();
    });

    expect(turnApi.calls.cancelRun).toHaveBeenCalledWith("lg-thread-1", "run-1");
    expect(stream.calls.stop).toHaveBeenCalledTimes(1);
    expect(
      turnApi.calls.cancelRun.mock.invocationCallOrder[0],
    ).toBeLessThan(stream.calls.stop.mock.invocationCallOrder[0]);
  });

  test("clears local linkage and starts fresh when the stream reports interrupts", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          langgraphThreadId: "lg-thread-1",
          updatedAt: 100,
        } as Thread,
      ],
    });
    const persistence = createPersistenceHarness();
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        persistence,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    stream.setState({ interrupts: [{ value: "needs review" }] });

    await waitFor(() => {
      expect(result.current.selectedThread).toBeNull();
      expect(persistence.calls.clearAll).toHaveBeenCalled();
      expect(stream.calls.switchThread).toHaveBeenCalledWith(null);
      expect(result.current.statusNote).toMatch(/unexpected pause/i);
    });
  });
});
