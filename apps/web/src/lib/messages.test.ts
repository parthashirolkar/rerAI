import { describe, expect, test } from "bun:test";

import {
  extractThreadStateMessages,
  extractMessageText,
  getMessageKey,
  getMessageTimestamp,
  isAssistantMessage,
  isUserMessage,
} from "./messages";

describe("message helpers", () => {
  test("supports flattened messages", () => {
    const message = {
      type: "ai",
      id: "flat-ai",
      content: "done",
      createdAt: 123,
    };

    expect(isAssistantMessage(message)).toBe(true);
    expect(extractMessageText(message)).toBe("done");
    expect(getMessageKey(message, 0)).toBe("flat-ai");
    expect(getMessageTimestamp(message)).toBe(123);
  });

  test("supports nested LangChain message_to_dict output", () => {
    const message = {
      type: "ai",
      data: {
        type: "ai",
        id: "nested-ai",
        content: "nested content",
      },
    };

    expect(isAssistantMessage(message)).toBe(true);
    expect(extractMessageText(message)).toBe("nested content");
    expect(getMessageKey(message, 0)).toBe("nested-ai");
  });

  test("supports nested human message content", () => {
    const message = {
      type: "human",
      data: {
        type: "human",
        content: "hello",
      },
    };

    expect(isUserMessage(message)).toBe(true);
    expect(extractMessageText(message)).toBe("hello");
  });

  test("falls back to nested timestamps", () => {
    const message = {
      type: "ai",
      data: {
        type: "ai",
        content: "done",
        _creationTime: 456,
      },
    };

    expect(getMessageTimestamp(message)).toBe(456);
  });

  test("extracts usable messages from final thread state values", () => {
    const state = {
      values: {
        messages: [
          { type: "human", content: "hello" },
          { type: "ai", id: "ai-1", content: "done" },
          { type: "system", content: "ignore" },
        ],
      },
    };

    const messages = extractThreadStateMessages(state);

    expect(messages).toHaveLength(2);
    expect(extractMessageText(messages[1])).toBe("done");
  });

  test("returns no messages when final thread state is missing values", () => {
    expect(extractThreadStateMessages({ values: {} })).toEqual([]);
    expect(extractThreadStateMessages(null)).toEqual([]);
  });
});
