import { Client } from "@langchain/langgraph-sdk";

export const ASSISTANT_ID = "rerai";

const THREAD_STORAGE_KEY = "rerai.thread-id";
const RUN_STORAGE_KEY = "rerai.active-run-id";

function trimTrailingSlash(value: string) {
  return value.replace(/\/$/, "");
}

function resolveBackendUrl() {
  const backendUrl = import.meta.env.VITE_BACKEND_URL?.trim();
  if (!backendUrl) {
    throw new Error("Missing VITE_BACKEND_URL");
  }
  return trimTrailingSlash(backendUrl);
}

const API_URL = resolveBackendUrl();

export function createLangGraphClient(authToken: string | null) {
  return new Client({
    apiUrl: API_URL,
    callerOptions: {
      fetch: (input: string | URL | globalThis.Request, init?: RequestInit) => {
        const headers = new Headers(init?.headers);
        if (authToken) {
          headers.set("Authorization", `Bearer ${authToken}`);
        }

        return fetch(input, {
          ...init,
          headers,
        });
      },
    },
  });
}

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
