import { Client } from "@langchain/langgraph-sdk";

export const ASSISTANT_ID = "rerai";

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

export function createLangGraphClient(authToken: string | null) {
  const apiUrl = resolveBackendUrl();

  return new Client({
    apiUrl,
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
