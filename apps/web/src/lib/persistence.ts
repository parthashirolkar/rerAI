export interface SessionPersistence {
  getThreadId(): string | null;
  setThreadId(id: string | null): void;
  getRunId(): string | null;
  setRunId(id: string | null): void;
  clearAll(): void;
}

const THREAD_STORAGE_KEY = "rerai.thread-id";
const RUN_STORAGE_KEY = "rerai.active-run-id";

function readStorage(key: string): string | null {
  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }
  try {
    if (value) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // ignore quota exceeded or security errors
  }
}

export function createLocalStoragePersistence(): SessionPersistence {
  return {
    getThreadId() {
      return readStorage(THREAD_STORAGE_KEY);
    },
    setThreadId(id) {
      writeStorage(THREAD_STORAGE_KEY, id);
    },
    getRunId() {
      return readStorage(RUN_STORAGE_KEY);
    },
    setRunId(id) {
      writeStorage(RUN_STORAGE_KEY, id);
    },
    clearAll() {
      writeStorage(THREAD_STORAGE_KEY, null);
      writeStorage(RUN_STORAGE_KEY, null);
    },
  };
}

export function createMemoryPersistence(
  initial?: { threadId?: string | null; runId?: string | null },
): SessionPersistence {
  let threadId = initial?.threadId ?? null;
  let runId = initial?.runId ?? null;

  return {
    getThreadId() {
      return threadId;
    },
    setThreadId(id) {
      threadId = id;
    },
    getRunId() {
      return runId;
    },
    setRunId(id) {
      runId = id;
    },
    clearAll() {
      threadId = null;
      runId = null;
    },
  };
}
