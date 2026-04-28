import { describe, expect, test } from "bun:test";
import {
  createLocalStoragePersistence,
  createMemoryPersistence,
} from "./persistence";

describe("createMemoryPersistence", () => {
  test("get/set threadId", () => {
    const p = createMemoryPersistence();
    expect(p.getThreadId()).toBeNull();
    p.setThreadId("t1");
    expect(p.getThreadId()).toBe("t1");
  });

  test("get/set runId", () => {
    const p = createMemoryPersistence();
    expect(p.getRunId()).toBeNull();
    p.setRunId("r1");
    expect(p.getRunId()).toBe("r1");
  });

  test("clearAll wipes both", () => {
    const p = createMemoryPersistence({ threadId: "t1", runId: "r1" });
    expect(p.getThreadId()).toBe("t1");
    expect(p.getRunId()).toBe("r1");
    p.clearAll();
    expect(p.getThreadId()).toBeNull();
    expect(p.getRunId()).toBeNull();
  });

  test("initial values optional", () => {
    const p = createMemoryPersistence({ threadId: "t1" });
    expect(p.getThreadId()).toBe("t1");
    expect(p.getRunId()).toBeNull();
  });
});

describe("createLocalStoragePersistence", () => {
  test("operations do not throw when localStorage unavailable", () => {
    const p = createLocalStoragePersistence();
    expect(() => p.clearAll()).not.toThrow();
    expect(() => p.setThreadId("t1")).not.toThrow();
    expect(() => p.setRunId("r1")).not.toThrow();
    expect(() => p.getThreadId()).not.toThrow();
    expect(() => p.getRunId()).not.toThrow();
  });
});
