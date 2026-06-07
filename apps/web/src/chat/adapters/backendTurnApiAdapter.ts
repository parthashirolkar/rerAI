import { resolveBackendUrl } from "@/lib/langgraphClient";
import type {
  SubmittedTurn,
  TurnApiPort,
  TurnSubmission,
} from "../ports";

type BackendTurnResponse = {
  turn_id: string;
  human_message_id: string;
  thread_id: string;
  run_id: string;
};

async function requestJson<T>(
  authToken: string | null,
  path: string,
  init: RequestInit,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  const response = await fetch(`${resolveBackendUrl()}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail || `Backend request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function createBackendTurnApiAdapter(
  authToken: string | null,
): TurnApiPort {
  return {
    async submitTurn(payload: TurnSubmission): Promise<SubmittedTurn> {
      const result = await requestJson<BackendTurnResponse>(
        authToken,
        "/chat/turns",
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      );
      return {
        turnId: result.turn_id,
        humanMessageId: result.human_message_id,
        threadId: result.thread_id,
        runId: result.run_id,
      };
    },
    async cancelRun(threadId, runId) {
      return await requestJson(
        authToken,
        `/threads/${threadId}/runs/${runId}/cancel`,
        { method: "POST" },
      );
    },
  };
}
