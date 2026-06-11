import { act, renderHook, waitFor } from "@testing-library/react";
import { useCallback, useEffect, useState } from "react";
import { describe, expect, test, vi } from "vitest";

import { useChatOrchestrator } from "./useChatOrchestrator";
import type {
  BackendPort,
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
  };
};

function createBackendHarness(initial?: {
  viewer?: Viewer | null;
  threads?: Thread[];
  messages?: ChatMessage[];
  turns?: ConversationTurn[];
}): BackendHarness {
  let activeThreadId: string | null = null;
  let threads = initial?.threads ?? [];
  const messages = initial?.messages ?? [];
  const turns = initial?.turns ?? [];

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
  };

  return {
    calls,
    get viewer() {
      return initial?.viewer ?? { name: "Tester" };
    },
    get threads() {
      return threads;
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

function createStreamHarness(
  initial?: Partial<StreamState>,
  options?: { requireConfiguredThreadForJoin?: boolean },
): {
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

  const useStream: UseStreamAdapter = (config, nextCallbacks) => {
    callbacks = nextCallbacks;
    const [, forceRender] = useState(0);
    const joinStream = useCallback(
      async (runId: string) => {
        if (options?.requireConfiguredThreadForJoin && !config.threadId) {
          return;
        }
        await calls.joinStream(runId);
      },
      [config.threadId],
    );

    useEffect(() => {
      const listener = () => forceRender((value) => value + 1);
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    }, []);

    return {
      ...snapshot,
      joinStream,
    };
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
    const stream = createStreamHarness(
      {},
      { requireConfiguredThreadForJoin: true },
    );
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
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
    expect(stream.calls.submit).not.toHaveBeenCalled();
    expect(stream.calls.switchThread).toHaveBeenLastCalledWith("lg-thread-1");
    expect(stream.calls.joinStream).toHaveBeenCalledWith("run-1");

    await waitFor(() => {
      expect(result.current.selectedThread?._id).toBe("thread-1");
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
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
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
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
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
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
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

  test("does not finalize backend-owned turns from the browser", async () => {
    const backend = createBackendHarness();
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
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
  });

  test("reports a stream error without mutating durable turn state", async () => {
    const backend = createBackendHarness();
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    await act(async () => {
      await result.current.submitMessage("Check Kothrud");
    });

    await stream.emitError(new Error("LangGraph failed"));

    await waitFor(() => {
      expect(result.current.statusNote).toBe("LangGraph failed");
    });
  });

  test("stops the backend run before closing the local stream", async () => {
    const backend = createBackendHarness();
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
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

  test("stops a selected Live Turn using its persisted run identity", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });
    expect(result.current.canStop).toBe(true);
    await act(async () => {
      await result.current.stop();
    });

    expect(turnApi.calls.cancelRun).toHaveBeenCalledWith("lg-thread-1", "run-1");
  });

  test("keeps a Live Turn in a stopping state until cancellation resolves", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();
    let resolveCancellation:
      | ((value: { status: "cancelled" }) => void)
      | undefined;
    turnApi.calls.cancelRun.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCancellation = resolve;
        }),
    );

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });
    let stopPromise: Promise<void>;
    act(() => {
      stopPromise = result.current.stop();
    });

    expect(result.current.isStopping).toBe(true);

    await act(async () => {
      resolveCancellation?.({ status: "cancelled" });
      await stopPromise;
    });

    expect(result.current.isStopping).toBe(false);
  });

  test("keeps the selected conversation when the stream reports interrupt metadata", async () => {
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
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    stream.setState({ interrupts: [{ value: "needs review" }] });

    await waitFor(() => {
      expect(result.current.selectedThread?._id).toBe("thread-1");
    });
    expect(stream.calls.switchThread).not.toHaveBeenCalledWith(null);
    expect(result.current.statusNote).toBeNull();
  });

  test("reattaches a selected Live Turn after configuring its LangGraph thread", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness(
      {},
      { requireConfiguredThreadForJoin: true },
    );

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi: createTurnApiHarness(),
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    await waitFor(() => {
      expect(stream.calls.joinStream).toHaveBeenCalledWith("run-1");
    });
    expect(result.current.selectedThread?._id).toBe("thread-1");
  });

  test("derives busy state from the selected Live Turn", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi: createTurnApiHarness(),
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    expect(result.current.busy).toBe(true);
  });

  test("retries Live Turn attachment while its identifiers remain selected", async () => {
    vi.useFakeTimers();
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness(
      {},
      { requireConfiguredThreadForJoin: true },
    );
    stream.calls.joinStream
      .mockRejectedValueOnce(new Error("Disconnected"))
      .mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi: createTurnApiHarness(),
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });
    await vi.waitFor(() => {
      expect(stream.calls.joinStream).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(stream.calls.joinStream).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  test("reports reconnecting without deselecting the Conversation", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness(
      {},
      { requireConfiguredThreadForJoin: true },
    );
    stream.calls.joinStream.mockRejectedValue(new Error("Disconnected"));

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi: createTurnApiHarness(),
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    await waitFor(() => {
      expect(result.current.connectionStatus).toBe("reconnecting");
    });
    expect(result.current.selectedThread?._id).toBe("thread-1");
  });

  test("retries a failed turn as a new Conversation Turn", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "failed-turn",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "failed",
          errorMessage: "Run failed",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });
    await act(async () => {
      await result.current.retryTurn("failed-turn");
    });

    expect(turnApi.calls.submitTurn).toHaveBeenCalledWith({
      turnId: expect.not.stringMatching(/^failed-turn$/),
      humanMessageId: expect.any(String),
      uiThreadId: "thread-1",
      content: "Check Baner",
    });
  });

  test("shows a failed submission as failed and allows retry", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();
    turnApi.calls.submitTurn.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });
    await act(async () => {
      try {
        await result.current.submitMessage("Check Baner");
      } catch {
        // expected
      }
    });

    const failedTurn = result.current.turns.find(
      (t) => t.userContent === "Check Baner",
    );
    expect(failedTurn).toBeDefined();
    expect(failedTurn?.status).toBe("failed");
    expect(failedTurn?.errorMessage).toBe("Unable to submit");

    turnApi.calls.submitTurn.mockResolvedValue({
      turnId: "retry-turn",
      humanMessageId: "retry-human",
      threadId: "lg-thread-1",
      runId: "run-1",
    });
    await act(async () => {
      await result.current.retryTurn(failedTurn!.turnId);
    });

    expect(turnApi.calls.submitTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        uiThreadId: "thread-1",
        content: "Check Baner",
      }),
    );
  });

  test("rejects another submission while the Conversation has a Live Turn", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });
    await act(async () => {
      await result.current.submitMessage("Another request");
    });

    expect(turnApi.calls.submitTurn).not.toHaveBeenCalled();
  });

  test("cancels a running Agent Run before deleting its Conversation", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
          activeTurn: {
            status: "running",
            langgraphThreadId: "lg-thread-1",
            langgraphRunId: "run-1",
          },
        } as Thread,
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    await act(async () => {
      await result.current.deleteThread("thread-1");
    });

    expect(turnApi.calls.cancelRun).toHaveBeenCalledWith("lg-thread-1", "run-1");
    expect(backend.calls.removeThread).toHaveBeenCalledWith("thread-1");
    expect(
      turnApi.calls.cancelRun.mock.invocationCallOrder[0],
    ).toBeLessThan(backend.calls.removeThread.mock.invocationCallOrder[0]);
  });

  test("leaves conversation intact when cancellation fails during deletion", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
          activeTurn: {
            status: "running",
            langgraphThreadId: "lg-thread-1",
            langgraphRunId: "run-1",
          },
        } as Thread,
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();
    turnApi.calls.cancelRun.mockRejectedValueOnce(new Error("Cancel failed"));

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    await act(async () => {
      await result.current.deleteThread("thread-1");
    });

    expect(turnApi.calls.cancelRun).toHaveBeenCalledWith("lg-thread-1", "run-1");
    expect(backend.calls.removeThread).not.toHaveBeenCalled();
    expect(result.current.statusNote).toBe("Cancel failed");
  });

  test("reconciles live stream content with persisted by longest prefix", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [
            {
              id: "ai-1",
              langgraphMessageId: "lg-ai-1",
              messagePosition: 0,
              canonicalContent: "Researching Baner",
              createdAt: 100,
            },
          ],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    // Live stream has prefix of persisted content
    stream.setState({
      isLoading: true,
      messages: [
        {
          type: "ai",
          id: "lg-ai-1",
          content: "Researching",
          messagePosition: 0,
          createdAt: 100,
        },
      ],
    });

    const turn = result.current.turns[0];
    expect(turn?.assistantMessages).toHaveLength(1);
    expect(turn?.assistantMessages[0].canonicalContent).toBe("Researching Baner");
    expect(turn?.assistantMessages[0].displayOnlyContent).toBeUndefined();
  });

  test("shows display-only continuation when live stream exceeds persisted", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [
            {
              id: "ai-1",
              langgraphMessageId: "lg-ai-1",
              messagePosition: 0,
              canonicalContent: "Researching",
              createdAt: 100,
            },
          ],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    // Live stream has longer content than persisted
    stream.setState({
      isLoading: true,
      messages: [
        {
          type: "ai",
          id: "lg-ai-1",
          content: "Researching Baner",
          messagePosition: 0,
          createdAt: 100,
        },
      ],
    });

    const turn = result.current.turns[0];
    expect(turn?.assistantMessages).toHaveLength(1);
    expect(turn?.assistantMessages[0].canonicalContent).toBe("Researching");
    expect(turn?.assistantMessages[0].displayOnlyContent).toBe(" Baner");
  });

  test("ignores live stream when content diverges from persisted", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [
            {
              id: "ai-1",
              langgraphMessageId: "lg-ai-1",
              messagePosition: 0,
              canonicalContent: "Researching Baner",
              createdAt: 100,
            },
          ],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    // Live stream has completely different content
    stream.setState({
      isLoading: true,
      messages: [
        {
          type: "ai",
          id: "lg-ai-1",
          content: "Final assessment",
          messagePosition: 0,
          createdAt: 100,
        },
      ],
    });

    const turn = result.current.turns[0];
    expect(turn?.assistantMessages).toHaveLength(1);
    expect(turn?.assistantMessages[0].canonicalContent).toBe("Researching Baner");
    expect(turn?.assistantMessages[0].displayOnlyContent).toBeUndefined();
  });

  test("adds new live stream messages as display-only", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [
            {
              id: "ai-1",
              langgraphMessageId: "lg-ai-1",
              messagePosition: 0,
              canonicalContent: "Researching",
              createdAt: 100,
            },
          ],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    // Live stream has a new message not in persisted
    stream.setState({
      isLoading: true,
      messages: [
        {
          type: "ai",
          id: "lg-ai-2",
          content: "Final assessment",
          messagePosition: 1,
          createdAt: 200,
        },
      ],
    });

    const turn = result.current.turns[0];
    expect(turn?.assistantMessages).toHaveLength(2);
    expect(turn?.assistantMessages[0].canonicalContent).toBe("Researching");
    expect(turn?.assistantMessages[1].canonicalContent).toBe("");
    expect(turn?.assistantMessages[1].displayOnlyContent).toBe("Final assessment");
  });

  test("shows finalizing status when stream ends but turn is still running", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    await waitFor(() => {
      expect(stream.calls.joinStream).toHaveBeenCalledWith("run-1");
    });

    // Simulate stream loading then ending while turn still running
    stream.setState({
      isLoading: true,
      messages: [],
    });

    await waitFor(() => {
      expect(result.current.connectionStatus).toBe(null);
    });

    stream.setState({
      isLoading: false,
      messages: [],
    });

    await waitFor(() => {
      expect(result.current.connectionStatus).toBe("finalizing");
    });
  });

  test("clears finalizing status when turn becomes completed", async () => {
    const backend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "running",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [],
          createdAt: 100,
        },
      ],
    });
    const stream = createStreamHarness();
    const turnApi = createTurnApiHarness();

    const { result } = renderHook(() =>
      useChatOrchestrator({
        backend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result.current.selectThread("thread-1");
    });

    await waitFor(() => {
      expect(stream.calls.joinStream).toHaveBeenCalledWith("run-1");
    });

    // Simulate stream loading then ending while turn still running
    stream.setState({
      isLoading: true,
      messages: [],
    });

    await waitFor(() => {
      expect(result.current.connectionStatus).toBe(null);
    });

    stream.setState({
      isLoading: false,
      messages: [],
    });

    await waitFor(() => {
      expect(result.current.connectionStatus).toBe("finalizing");
    });

    // Now turn becomes completed
    const completedBackend = createBackendHarness({
      threads: [
        {
          _id: "thread-1",
          title: "Existing thread",
          updatedAt: 100,
        } as Thread,
      ],
      turns: [
        {
          turnId: "turn-1",
          threadId: "thread-1",
          turnPosition: 0,
          userContent: "Check Baner",
          status: "completed",
          langgraphThreadId: "lg-thread-1",
          langgraphRunId: "run-1",
          assistantMessages: [
            {
              id: "ai-1",
              langgraphMessageId: "lg-ai-1",
              messagePosition: 0,
              canonicalContent: "Researching Baner",
              createdAt: 100,
            },
          ],
          createdAt: 100,
        },
      ],
    });

    // Re-render with completed backend
    const { result: result2 } = renderHook(() =>
      useChatOrchestrator({
        backend: completedBackend,
        useStream: stream.useStream,
        authToken: "token",
        turnApi,
      }),
    );

    act(() => {
      result2.current.selectThread("thread-1");
    });

    await waitFor(() => {
      expect(result2.current.connectionStatus).toBe(null);
    });
  });
});
