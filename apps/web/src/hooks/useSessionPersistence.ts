import { useCallback, useEffect, useState } from "react";
import {
  createLocalStoragePersistence,
  type SessionPersistence,
} from "@/lib/persistence";

export type SessionSnapshot = {
  threadId: string | null;
  runId: string | null;
};

const globalPersistence = createLocalStoragePersistence();

export function useSessionPersistence(
  persistence: SessionPersistence = globalPersistence,
) {
  const [snapshot, setSnapshot] = useState<SessionSnapshot>(() => ({
    threadId: persistence.getThreadId(),
    runId: persistence.getRunId(),
  }));

  useEffect(() => {
    setSnapshot({
      threadId: persistence.getThreadId(),
      runId: persistence.getRunId(),
    });
  }, [persistence]);

  const setThreadId = useCallback(
    (id: string | null) => {
      persistence.setThreadId(id);
      setSnapshot((prev) => ({ ...prev, threadId: id }));
    },
    [persistence],
  );

  const setRunId = useCallback(
    (id: string | null) => {
      persistence.setRunId(id);
      setSnapshot((prev) => ({ ...prev, runId: id }));
    },
    [persistence],
  );

  const clear = useCallback(() => {
    persistence.clearAll();
    setSnapshot({ threadId: null, runId: null });
  }, [persistence]);

  return { snapshot, setThreadId, setRunId, clear };
}

export function clearSessionPersistence(): void {
  globalPersistence.clearAll();
}
