import { describe, expect, test } from "bun:test";
import {
  extractThreadMessages,
  normalizeMessages,
  selectLiveAssistantMessage,
  toAssistantMirrorPayload,
} from "./messages";

describe("normalizeMessages", () => {
  test("passes through Convex docs", () => {
    const result = normalizeMessages([
      { _id: "msg-1", role: "user", content: "hello", createdAt: 1000 },
      { _id: "msg-2", role: "assistant", content: "hi", createdAt: 2000 },
    ]);

    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({
      _id: "msg-1",
      role: "user",
      content: "hello",
      createdAt: 1000,
    });
    expect(result[1]).toEqual({
      _id: "msg-2",
      role: "assistant",
      content: "hi",
      createdAt: 2000,
    });
  });

  test("unwraps LangGraph stream chunks", () => {
    const result = normalizeMessages([
      {
        type: "ai",
        id: "ai-1",
        content: "nested content",
        data: { type: "ai", id: "ai-1", content: "nested content", createdAt: 3000 },
      },
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].role).toBe("assistant");
    expect(result[0].id).toBe("ai-1");
    expect(result[0].content).toBe("nested content");
    expect(result[0].createdAt).toBe(3000);
  });

  test("normalizes role aliases", () => {
    const result = normalizeMessages([
      { type: "human", content: "hello" },
      { type: "ai", content: "done" },
    ]);

    expect(result[0].role).toBe("user");
    expect(result[1].role).toBe("assistant");
  });

  test("flattens content block arrays", () => {
    const result = normalizeMessages([
      {
        role: "assistant",
        content: [{ type: "text", text: "hello" }, { type: "text", text: "world" }],
      },
    ]);

    expect(result[0].content).toBe("hello\nworld");
  });

  test("drops system and tool messages", () => {
    const result = normalizeMessages([
      { role: "user", content: "hello" },
      { role: "system", content: "ignore" },
      { role: "assistant", content: "done" },
      { role: "tool", content: "ignore" },
    ]);

    expect(result).toHaveLength(2);
    expect(result[0].role).toBe("user");
    expect(result[1].role).toBe("assistant");
  });

  test("handles mixed arrays", () => {
    const result = normalizeMessages([
      { _id: "convex-1", role: "user", content: "from convex", createdAt: 100 },
      { type: "ai", content: "from langgraph", createdAt: 200 },
    ]);

    expect(result).toHaveLength(2);
    expect(result[0].content).toBe("from convex");
    expect(result[1].content).toBe("from langgraph");
  });

  test("filters null and undefined elements", () => {
    const result = normalizeMessages([null, undefined, { role: "user", content: "ok" }]);
    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("ok");
  });

  test("falls back to Date.now() for missing timestamps", () => {
    const before = Date.now();
    const result = normalizeMessages([{ role: "user", content: "hello" }]);
    const after = Date.now();
    expect(result[0].createdAt).toBeGreaterThanOrEqual(before);
    expect(result[0].createdAt).toBeLessThanOrEqual(after);
  });

  test("falls back to nested timestamps", () => {
    const result = normalizeMessages([
      {
        type: "ai",
        data: { type: "ai", content: "done", _creationTime: 456 },
      },
    ]);
    expect(result[0].createdAt).toBe(456);
  });

  test("returns empty array for empty input", () => {
    expect(normalizeMessages([])).toEqual([]);
  });
});

describe("extractThreadMessages", () => {
  test("extracts from thread state values", () => {
    const state = {
      values: {
        messages: [
          { type: "human", content: "hello" },
          { type: "ai", id: "ai-1", content: "done" },
          { type: "system", content: "ignore" },
        ],
      },
    };

    const result = extractThreadMessages(state);
    expect(result).toHaveLength(2);
    expect(result[0].role).toBe("user");
    expect(result[1].role).toBe("assistant");
    expect(result[1].id).toBe("ai-1");
  });

  test("returns empty for missing values", () => {
    expect(extractThreadMessages({ values: {} })).toEqual([]);
    expect(extractThreadMessages(null)).toEqual([]);
    expect(extractThreadMessages(undefined)).toEqual([]);
  });
});

describe("toAssistantMirrorPayload", () => {
  test("filters to assistant and skips empty", () => {
    const payload = toAssistantMirrorPayload([
      { role: "user", content: "hello", createdAt: 100 },
      { role: "assistant", content: "", createdAt: 200, id: "a1" },
      { role: "assistant", content: "  ", createdAt: 300, id: "a2" },
      { role: "assistant", content: "done", createdAt: 400, id: "a3" },
    ]);

    expect(payload).toHaveLength(1);
    expect(payload[0]).toEqual({
      langgraphMessageId: "a3",
      content: "done",
      createdAt: 400,
    });
  });

  test("strips blank langgraphMessageId", () => {
    const payload = toAssistantMirrorPayload([
      { role: "assistant", content: "ok", createdAt: 100, id: "" },
    ]);

    expect(payload[0].langgraphMessageId).toBeUndefined();
  });

  test("round-trip preserves fields", () => {
    const raw = [
      { type: "ai", id: "lg-1", content: "hello", createdAt: 1000 },
      { type: "ai", id: "lg-2", content: "world", createdAt: 2000 },
    ];
    const normalized = normalizeMessages(raw);
    const payload = toAssistantMirrorPayload(normalized);

    expect(payload).toEqual([
      { langgraphMessageId: "lg-1", content: "hello", createdAt: 1000 },
      { langgraphMessageId: "lg-2", content: "world", createdAt: 2000 },
    ]);
  });
});

describe("selectLiveAssistantMessage", () => {
  test("ignores an already persisted assistant while a follow-up is pending", () => {
    const persisted = [
      { role: "user" as const, content: "first", createdAt: 100 },
      {
        role: "assistant" as const,
        content: "old answer",
        createdAt: 200,
        id: "ai-old",
        langgraphMessageId: "ai-old",
      },
      { role: "user" as const, content: "follow up", createdAt: 300 },
    ];
    const stream = [
      { role: "assistant" as const, content: "old answer", createdAt: 200, id: "ai-old" },
    ];

    expect(selectLiveAssistantMessage(persisted, stream)).toBeNull();
  });

  test("returns a new assistant stream chunk with a new LangGraph id", () => {
    const persisted = [
      {
        role: "assistant" as const,
        content: "old answer",
        createdAt: 200,
        id: "ai-old",
      },
    ];
    const next = {
      role: "assistant" as const,
      content: "new answer",
      createdAt: 400,
      id: "ai-new",
    };

    expect(selectLiveAssistantMessage(persisted, [next])).toEqual(next);
  });

  test("ignores id-less stream content already represented in persisted messages", () => {
    const persisted = [
      { role: "assistant" as const, content: "same answer", createdAt: 200 },
    ];
    const stream = [
      { role: "assistant" as const, content: "same answer", createdAt: 300 },
    ];

    expect(selectLiveAssistantMessage(persisted, stream)).toBeNull();
  });

  test("returns id-less stream content when it is new", () => {
    const persisted = [
      { role: "assistant" as const, content: "old answer", createdAt: 200 },
    ];
    const next = {
      role: "assistant" as const,
      content: "new answer",
      createdAt: 300,
    };

    expect(selectLiveAssistantMessage(persisted, [next])).toEqual(next);
  });
});
