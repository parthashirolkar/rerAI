export const API_URL = import.meta.env.VITE_LANGGRAPH_API_URL ?? "http://localhost:8123";
export const ASSISTANT_ID = "rerai";

const THREAD_STORAGE_KEY = "rerai.thread-id";
const RUN_STORAGE_KEY = "rerai.active-run-id";

function readStorage(key: string) {
  if (typeof window === "undefined") {
    return null;
  }

  return window.localStorage.getItem(key);
}

function writeStorage(key: string, value: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (value) {
    window.localStorage.setItem(key, value);
    return;
  }

  window.localStorage.removeItem(key);
}

export function getPersistedThreadId() {
  return readStorage(THREAD_STORAGE_KEY);
}

export function persistThreadId(threadId: string | null) {
  writeStorage(THREAD_STORAGE_KEY, threadId);
}

export function clearPersistedThreadId() {
  writeStorage(THREAD_STORAGE_KEY, null);
}

export function getPersistedRunId() {
  return readStorage(RUN_STORAGE_KEY);
}

export function persistRunId(runId: string | null) {
  writeStorage(RUN_STORAGE_KEY, runId);
}

export function clearPersistedRunId() {
  writeStorage(RUN_STORAGE_KEY, null);
}
