import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  normalizeMessages,
  selectLiveAssistantMessage,
  selectLiveAssistantMessages,
} from "@/lib/messages";
import type { ChatMessage, ConversationTurn, AssistantMessage } from "@/lib/messages";
import type {
  UseChatOrchestratorOptions,
  ChatOrchestratorState,
  ChatOrchestratorActions,
} from "./ports";

type OptimisticMessage = ChatMessage & {
  localOnly: true;
  threadId: string;
};

type ActiveTurn = {
  turnId: string;
  humanMessageId: string;
  threadId: string;
  userContent: string;
  turnPosition: number;
  createdAt: number;
};

type DesiredAttachment = {
  conversationId: string;
  turnId: string;
  threadId: string;
  runId: string;
};

const MAX_ATTACHMENT_ATTEMPTS = 4;
const ATTACHMENT_RETRY_BASE_MS = 500;

type SubmitTiming = {
  startedAt: number;
  marks: Array<{ label: string; at: number }>;
  firstChunkLogged: boolean;
};

function chatTimingEnabled() {
  return (
    import.meta.env.DEV ||
    globalThis.localStorage?.getItem("rerai:chatTimings") === "1"
  );
}

function createSubmitTiming(): SubmitTiming {
  return {
    startedAt: performance.now(),
    marks: [],
    firstChunkLogged: false,
  };
}

function markSubmitTiming(timing: SubmitTiming | null, label: string) {
  if (!timing) {
    return;
  }
  timing.marks.push({ label, at: performance.now() });
}

function logSubmitTiming(_timing: SubmitTiming | null, _label: string) {
  // No-op: removed console.table debugging
}

function hasPersistedEquivalent(
  persistedMessages: ChatMessage[],
  message: OptimisticMessage,
) {
  return persistedMessages.some(
    (persistedMessage) =>
      persistedMessage.role === message.role &&
      persistedMessage.content.trim() === message.content.trim(),
  );
}

function orderTranscriptMessages(messages: ChatMessage[]) {
  return messages
    .map((message, index) => ({ message, index }))
    .sort((left, right) => {
      const timeDelta = left.message.createdAt - right.message.createdAt;
      return timeDelta === 0 ? left.index - right.index : timeDelta;
    })
    .map(({ message }) => message);
}

export function useChatOrchestrator({
  backend,
  useStream,
  authToken,
  turnApi,
}: UseChatOrchestratorOptions): ChatOrchestratorState & ChatOrchestratorActions {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [langgraphThreadId, setLanggraphThreadId] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState("");
  const [submitInFlight, setSubmitInFlight] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [optimisticMessages, setOptimisticMessages] = useState<OptimisticMessage[]>([]);
  const [activeTurn, setActiveTurn] = useState<ActiveTurn | null>(null);
  const [failedSubmissions, setFailedSubmissions] = useState<Map<string, string>>(new Map());
  const [desiredAttachment, setDesiredAttachment] =
    useState<DesiredAttachment | null>(null);
  const [attachmentAttempt, setAttachmentAttempt] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState<
    "connecting" | "reconnecting" | "finalizing" | null
  >(null);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);

  const submitTimingRef = useRef<SubmitTiming | null>(null);

  // Sync active thread to backend adapter
  useEffect(() => {
    backend.setActiveThread(selectedThreadId);
  }, [backend, selectedThreadId]);

  const streamCallbacks = useMemo(
    () => ({
      onThreadId(nextThreadId: string) {
        setLanggraphThreadId(nextThreadId);
      },
      onCreated() {},
      onFinish() {
        setStatusNote("");
      },
      onStop() {
        setStatusNote("");
      },
      onError(error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        setStatusNote(message);
      },
    }),
    [],
  );

  const stream = useStream(
    { authToken, threadId: langgraphThreadId },
    streamCallbacks,
  );

  const wasLoadingRef = useRef(stream.isLoading);
  const joinStreamRef = useRef(stream.joinStream);
  joinStreamRef.current = stream.joinStream;

  const selectThread = useCallback(
    (threadId: string | null) => {
      const thread = backend.threads?.find((t) => t._id === threadId) ?? null;
      const nextLanggraphThreadId = thread?.langgraphThreadId ?? null;
      setSelectedThreadId(threadId);
      setLanggraphThreadId(nextLanggraphThreadId);
      setDesiredAttachment(null);
      setAttachmentAttempt(0);
      setConnectionStatus(null);
      setStatusNote("");
      stream.switchThread(nextLanggraphThreadId);
    },
    [backend, stream],
  );

  const selectedLiveTurn = useMemo(() => {
    if (!selectedThreadId) {
      return null;
    }
    return (
      [...(backend.turns ?? [])]
        .reverse()
        .find(
          (turn) =>
            (turn.status === "pending" || turn.status === "running") &&
            (!turn.threadId || turn.threadId === selectedThreadId),
        ) ?? null
    );
  }, [backend.turns, selectedThreadId]);

  useEffect(() => {
    if (!selectedThreadId) {
      setDesiredAttachment(null);
      return;
    }
    if (
      selectedLiveTurn?.status !== "running" ||
      !selectedLiveTurn.langgraphThreadId ||
      !selectedLiveTurn.langgraphRunId
    ) {
      if (desiredAttachment?.conversationId !== selectedThreadId) {
        setDesiredAttachment(null);
        setConnectionStatus(null);
      }
      return;
    }

    if (
      desiredAttachment?.conversationId === selectedThreadId &&
      desiredAttachment.turnId === selectedLiveTurn.turnId &&
      desiredAttachment.threadId === selectedLiveTurn.langgraphThreadId &&
      desiredAttachment.runId === selectedLiveTurn.langgraphRunId
    ) {
      return;
    }

    setLanggraphThreadId(selectedLiveTurn.langgraphThreadId);
    setDesiredAttachment({
      conversationId: selectedThreadId,
      turnId: selectedLiveTurn.turnId,
      threadId: selectedLiveTurn.langgraphThreadId,
      runId: selectedLiveTurn.langgraphRunId,
    });
    setAttachmentAttempt(0);
    setConnectionStatus("connecting");
  }, [desiredAttachment, selectedLiveTurn, selectedThreadId]);

  useEffect(() => {
    if (
      !desiredAttachment ||
      desiredAttachment.conversationId !== selectedThreadId ||
      desiredAttachment.threadId !== langgraphThreadId
    ) {
      return;
    }

    let stale = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    void joinStreamRef.current(desiredAttachment.runId)
      .then(() => {
        if (!stale) {
          setStatusNote("");
          setConnectionStatus(null);
        }
      })
      .catch(() => {
        if (stale) {
          return;
        }
        setConnectionStatus("reconnecting");
        if (attachmentAttempt + 1 < MAX_ATTACHMENT_ATTEMPTS) {
          retryTimer = setTimeout(() => {
            setAttachmentAttempt((attempt) => attempt + 1);
          }, ATTACHMENT_RETRY_BASE_MS * 2 ** attachmentAttempt);
        }
      });
    return () => {
      stale = true;
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
    };
  }, [
    attachmentAttempt,
    desiredAttachment,
    langgraphThreadId,
    selectedThreadId,
  ]);

  useEffect(() => {
    const wasLoading = wasLoadingRef.current;
    const isLoading = stream.isLoading;
    wasLoadingRef.current = isLoading;

    if (wasLoading && !isLoading && selectedLiveTurn?.status === "running") {
      setConnectionStatus("finalizing");
    }
    if (selectedLiveTurn?.status && selectedLiveTurn.status !== "running") {
      setConnectionStatus((current) => {
        if (current === "finalizing") {
          return null;
        }
        return current;
      });
    }
  }, [stream.isLoading, selectedLiveTurn]);

  const createThread = useCallback(async () => {
    const thread = await backend.createThread();
    selectThread(thread._id);
  }, [backend, selectThread]);

  const deleteThread = useCallback(
    async (threadId: string) => {
      const thread = backend.threads?.find((candidate) => candidate._id === threadId);
      setDeletingThreadId(threadId);
      try {
        if (thread?.activeTurn) {
          const { langgraphThreadId, langgraphRunId } = thread.activeTurn;
          if (
            thread.activeTurn.status !== "running" ||
            !langgraphThreadId ||
            !langgraphRunId ||
            !turnApi
          ) {
            setStatusNote(
              "This conversation is still starting and cannot be deleted yet.",
            );
            return;
          }
          await turnApi.cancelRun(langgraphThreadId, langgraphRunId);
        }
        await backend.removeThread(threadId);
        if (threadId === selectedThreadId) {
          selectThread(null);
        }
      } catch (error) {
        setStatusNote(error instanceof Error ? error.message : String(error));
      } finally {
        setDeletingThreadId(null);
      }
    },
    [backend, selectThread, selectedThreadId, turnApi],
  );

  const submitMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) {
        return;
      }
      if (selectedLiveTurn) {
        return;
      }

      setSubmitInFlight(true);
      submitTimingRef.current = createSubmitTiming();

      let nextThread = backend.threads?.find((t) => t._id === selectedThreadId) ?? null;
      if (!nextThread) {
        nextThread = await backend.createThread();
        markSubmitTiming(submitTimingRef.current, "convex:createThread");
        selectThread(nextThread._id);
      }

      stream.switchThread(nextThread.langgraphThreadId ?? null);
      markSubmitTiming(submitTimingRef.current, "stream:switchThread");

      setOptimisticMessages((current) => [
        ...current,
        {
          id: `local-${Date.now()}`,
          localOnly: true,
          threadId: nextThread._id,
          role: "user",
          content: trimmed,
          createdAt: Date.now(),
        },
      ]);

      setStatusNote("");

      let turnId: string | undefined;
      let humanMessageId: string | undefined;

      try {
        if (turnApi) {
          turnId = globalThis.crypto.randomUUID();
          humanMessageId = globalThis.crypto.randomUUID();
          setActiveTurn({
            turnId,
            humanMessageId,
            threadId: nextThread._id,
            userContent: trimmed,
            turnPosition:
              Math.max(
                -1,
                ...(backend.turns ?? []).map((turn) => turn.turnPosition),
              ) + 1,
            createdAt: Date.now(),
          });
          const submitted = await turnApi.submitTurn({
            turnId,
            humanMessageId,
            uiThreadId: nextThread._id,
            content: trimmed,
          });
          setLanggraphThreadId(submitted.threadId);
          stream.switchThread(submitted.threadId);
          setDesiredAttachment({
            conversationId: nextThread._id,
            turnId: submitted.turnId,
            threadId: submitted.threadId,
            runId: submitted.runId,
          });
          return;
        }

        await stream.submit(
          { messages: [{ type: "human", content: trimmed }] },
          { streamResumable: true, onDisconnect: "continue" },
        );
        markSubmitTiming(submitTimingRef.current, "stream:submitReturned");
      } catch (error) {
        if (turnApi && turnId) {
          setFailedSubmissions((current) => new Map(current).set(turnId, trimmed));
        }
        throw error;
      } finally {
        setSubmitInFlight(false);
      }
    },
    [backend, selectedLiveTurn, selectedThreadId, selectThread, stream, turnApi],
  );

  const stop = useCallback(async () => {
    const threadId =
      selectedLiveTurn?.langgraphThreadId ?? desiredAttachment?.threadId;
    const runId = selectedLiveTurn?.langgraphRunId ?? desiredAttachment?.runId;
    setIsStopping(true);
    try {
      if (turnApi && threadId && runId) {
        await turnApi.cancelRun(threadId, runId);
      }
      await stream.stop();
    } finally {
      setIsStopping(false);
    }
  }, [desiredAttachment, selectedLiveTurn, stream, turnApi]);

  const retryTurn = useCallback(
    async (turnId: string) => {
      const turn = (backend.turns ?? []).find(
        (candidate) => candidate.turnId === turnId,
      );
      const content = turn?.userContent ?? failedSubmissions.get(turnId);
      if (!content) {
        return;
      }
      if (turn && turn.status !== "failed" && !failedSubmissions.has(turnId)) {
        return;
      }
      await submitMessage(content);
      setFailedSubmissions((current) => {
        const next = new Map(current);
        next.delete(turnId);
        return next;
      });
    },
    [backend.turns, failedSubmissions, submitMessage],
  );

  const reconnect = useCallback(() => {
    if (!desiredAttachment) {
      return;
    }
    setConnectionStatus("connecting");
    setAttachmentAttempt(0);
  }, [desiredAttachment]);

  // Auto-deselect deleted threads
  useEffect(() => {
    if (!selectedThreadId) {
      return;
    }
    const exists = backend.threads?.some((thread) => thread._id === selectedThreadId);
    if (!exists) {
      selectThread(null);
    }
  }, [selectedThreadId, selectThread, backend.threads]);

  const normalizedStreamMessages = useMemo(
    () => normalizeMessages(stream.messages),
    [stream.messages],
  );

  const liveAssistantMessage = useMemo(() => {
    if (!stream.isLoading) {
      return null;
    }
    return selectLiveAssistantMessage(backend.messages ?? [], normalizedStreamMessages);
  }, [backend.messages, stream.isLoading, normalizedStreamMessages]);

  const liveAssistantMessages = useMemo(() => {
    const persisted = (backend.turns ?? []).flatMap((turn) =>
      turn.assistantMessages.map((message) => ({
        id: message.id,
        langgraphMessageId: message.langgraphMessageId,
        role: "assistant" as const,
        content: `${message.canonicalContent}${message.displayOnlyContent ?? ""}`,
        createdAt: message.createdAt,
        messagePosition: message.messagePosition,
      })),
    );
    return selectLiveAssistantMessages(persisted, normalizedStreamMessages);
  }, [backend.turns, normalizedStreamMessages]);

  useEffect(() => {
    if (!activeTurn) {
      return;
    }
    const persisted = (backend.turns ?? []).find(
      (turn) => turn.turnId === activeTurn.turnId,
    );
    if (
      persisted &&
      (persisted.status === "completed" ||
        persisted.status === "failed" ||
        persisted.status === "cancelled")
    ) {
      setActiveTurn(null);
    }
  }, [activeTurn, backend.turns]);

  const showThinking =
    stream.isLoading &&
    !liveAssistantMessage &&
    ((backend.messages?.length ?? 0) > 0 ||
      optimisticMessages.some((message) => message.threadId === selectedThreadId));

  useEffect(() => {
    const timing = submitTimingRef.current;
    if (!stream.isLoading || !timing || timing.firstChunkLogged || !liveAssistantMessage) {
      return;
    }
    timing.firstChunkLogged = true;
    logSubmitTiming(timing, "stream:firstAssistantChunk");
  }, [liveAssistantMessage, stream.isLoading]);

  useEffect(() => {
    const persisted = backend.messages ?? [];
    if (optimisticMessages.length === 0 || persisted.length === 0) {
      return;
    }
    setOptimisticMessages((current) => {
      const next = current.filter(
        (message) => !hasPersistedEquivalent(persisted, message),
      );
      return next.length === current.length ? current : next;
    });
  }, [backend.messages, optimisticMessages.length]);

  const displayMessages = useMemo(() => {
    const persisted = backend.messages ?? [];
    const activeThreadOptimistic = optimisticMessages.filter(
      (message) =>
        message.threadId === selectedThreadId &&
        !hasPersistedEquivalent(persisted, message),
    );
    if (!liveAssistantMessage) {
      return orderTranscriptMessages([...persisted, ...activeThreadOptimistic]);
    }
    return orderTranscriptMessages([
      ...persisted,
      ...activeThreadOptimistic,
      liveAssistantMessage,
    ]);
  }, [backend.messages, liveAssistantMessage, optimisticMessages, selectedThreadId]);

  const displayTurns = useMemo(() => {
    const turns = [...(backend.turns ?? [])].sort(
      (left, right) => left.turnPosition - right.turnPosition,
    );
    const liveTurn = activeTurn ?? selectedLiveTurn;
    if (!liveTurn || liveTurn.threadId !== selectedThreadId) {
      return turns;
    }

    const existingIndex = turns.findIndex(
      (turn) => turn.turnId === liveTurn.turnId,
    );
    const failedContent = activeTurn ? failedSubmissions.get(activeTurn.turnId) : undefined;
    const existing = existingIndex === -1 ? null : turns[existingIndex];

    const persistedByPosition = new Map(
      (existing?.assistantMessages ?? []).map((message) => [
        message.messagePosition,
        message,
      ]),
    );

    const liveMessages: AssistantMessage[] = [];
    for (const message of liveAssistantMessages) {
      const position = message.messagePosition ?? 0;
      const persisted = persistedByPosition.get(position);
      if (persisted) {
        const liveContent = message.content.trim();
        const persistedContent = persisted.canonicalContent.trim();
        if (liveContent === persistedContent) {
          continue;
        }
        if (persistedContent.startsWith(liveContent)) {
          continue;
        }
        if (liveContent.startsWith(persistedContent)) {
          liveMessages.push({
            id: persisted.id,
            langgraphMessageId:
              message.langgraphMessageId ?? message.id ?? persisted.langgraphMessageId,
            messagePosition: position,
            canonicalContent: persisted.canonicalContent,
            displayOnlyContent: liveContent.slice(persistedContent.length),
            createdAt: message.createdAt,
          });
          continue;
        }
        continue;
      }
      liveMessages.push({
        id:
          message.id ??
          message.langgraphMessageId ??
          `${liveTurn.turnId}-assistant-${liveMessages.length}`,
        langgraphMessageId: message.langgraphMessageId ?? message.id,
        messagePosition: position,
        canonicalContent: "",
        displayOnlyContent: message.content,
        createdAt: message.createdAt,
      });
    }

    if (existingIndex === -1) {
      return [
        ...turns,
        {
          turnId: liveTurn.turnId,
          turnPosition: activeTurn ? activeTurn.turnPosition : liveTurn.turnPosition,
          userContent: activeTurn ? activeTurn.userContent : liveTurn.userContent,
          status: failedContent ? "failed" : (stream.isLoading ? "running" : "pending"),
          assistantMessages: liveMessages,
          createdAt: activeTurn ? activeTurn.createdAt : liveTurn.createdAt,
          errorMessage: failedContent ? "Unable to submit" : undefined,
        } satisfies ConversationTurn,
      ];
    }

    const messagesByPosition = new Map(
      existing.assistantMessages.map((message) => [message.messagePosition, message]),
    );
    for (const message of liveMessages) {
      messagesByPosition.set(message.messagePosition, message);
    }
    turns[existingIndex] = {
      ...existing,
      assistantMessages: [...messagesByPosition.values()].sort(
        (left, right) => left.messagePosition - right.messagePosition,
      ),
    };
    return turns;
  }, [
    activeTurn,
    backend.turns,
    liveAssistantMessages,
    selectedThreadId,
    selectedLiveTurn,
    stream.isLoading,
    failedSubmissions,
  ]);

  const busy =
    submitInFlight ||
    isStopping ||
    stream.isLoading ||
    selectedLiveTurn?.status === "pending" ||
    selectedLiveTurn?.status === "running";
  const canStop =
    Boolean(
      selectedLiveTurn?.status === "running" &&
        selectedLiveTurn.langgraphThreadId &&
        selectedLiveTurn.langgraphRunId,
    ) ||
    Boolean(
      desiredAttachment &&
        desiredAttachment.conversationId === selectedThreadId,
    );
  const isInterrupted = false;

  const selectedThread = useMemo(
    () => backend.threads?.find((thread) => thread._id === selectedThreadId) ?? null,
    [backend.threads, selectedThreadId],
  );

  return {
    viewer: backend.viewer ?? null,
    threads: backend.threads ?? [],
    selectedThread,
    messages: displayMessages,
    turns: displayTurns,
    isStreaming: stream.isLoading,
    isStopping,
    canStop,
    connectionStatus,
    deletingThreadId,
    showThinking,
    busy,
    statusNote: statusNote || null,
    streamError: stream.error,
    isInterrupted,
    selectThread,
    createThread,
    deleteThread,
    submitMessage,
    retryTurn,
    stop,
    reconnect,
  };
}
