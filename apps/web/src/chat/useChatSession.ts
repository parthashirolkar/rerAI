import { useMemo, useEffect, useState, useCallback } from "react";
import { useAuthToken } from "@convex-dev/auth/react";
import { useConvexAuth } from "convex/react";
import { useChatOrchestrator } from "./useChatOrchestrator";
import { useConvexBackendAdapter } from "./adapters/convexBackendAdapter";
import { useLangGraphStreamAdapter } from "./adapters/langGraphStreamAdapter";
import { createLocalStoragePersistenceAdapter } from "./adapters/localStoragePersistenceAdapter";
import type { ChatOrchestratorState, ChatOrchestratorActions } from "./ports";

export function useChatSession(): ChatOrchestratorState & ChatOrchestratorActions {
  const authToken = useAuthToken();
  const { isAuthenticated } = useConvexAuth();
  const [viewerReady, setViewerReady] = useState(false);
  const [statusNote, setStatusNote] = useState("");

  const backend = useConvexBackendAdapter(viewerReady);
  const persistence = useMemo(() => createLocalStoragePersistenceAdapter(), []);

  const ensureViewer = useCallback(async () => {
    try {
      await backend.ensureViewer();
      setViewerReady(true);
    } catch (error) {
      setStatusNote(error instanceof Error ? error.message : String(error));
      setViewerReady(false);
    }
  }, [backend]);

  useEffect(() => {
    if (!isAuthenticated) {
      setViewerReady(false);
      persistence.clearAll();
      return;
    }
    void ensureViewer();
  }, [isAuthenticated, persistence, ensureViewer]);

  const orchestrator = useChatOrchestrator({
    backend,
    persistence,
    useStream: useLangGraphStreamAdapter,
    authToken,
  });

  return {
    ...orchestrator,
    statusNote: statusNote || orchestrator.statusNote,
  };
}
