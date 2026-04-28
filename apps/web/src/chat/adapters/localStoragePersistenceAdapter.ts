import {
  createLocalStoragePersistence,
  type SessionPersistence,
} from "@/lib/persistence";
import type { PersistencePort } from "../ports";

export function createLocalStoragePersistenceAdapter(): PersistencePort {
  const persistence: SessionPersistence = createLocalStoragePersistence();

  return {
    getThreadId() {
      return persistence.getThreadId();
    },
    setThreadId(id) {
      persistence.setThreadId(id);
    },
    getRunId() {
      return persistence.getRunId();
    },
    setRunId(id) {
      persistence.setRunId(id);
    },
    clearAll() {
      persistence.clearAll();
    },
  };
}
