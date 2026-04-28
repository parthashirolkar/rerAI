import type { Id } from "@convex-generated/dataModel";

export type ChatMessage = {
  _id?: Id<"uiMessages">;
  id?: string;
  langgraphMessageId?: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
};

export type AssistantMirrorPayload = {
  langgraphMessageId?: string;
  content: string;
  createdAt: number;
};

type MessageLike = {
  content?: unknown;
  id?: string;
  _id?: string;
  langgraphMessageId?: string;
  role?: string;
  type?: string;
  createdAt?: number;
  _creationTime?: number;
  getType?: () => string;
  _getType?: () => string;
  data?: MessageLike;
};

type ThreadStateLike = {
  values?: {
    messages?: unknown;
  };
};

type ContentBlock = {
  text?: string;
  type?: string;
};

function getMessageType(message: MessageLike): string {
  const nestedType = message.data?.type;
  return (
    message.getType?.() ??
    message._getType?.() ??
    message.role ??
    message.type ??
    nestedType ??
    "unknown"
  ).toLowerCase();
}

function getNestedMessage(message: unknown): MessageLike | null {
  if (!message || typeof message !== "object") {
    return null;
  }
  const candidate = message as MessageLike;
  if (candidate.data && typeof candidate.data === "object") {
    return candidate.data;
  }
  return null;
}

function getMessageContent(message: MessageLike): unknown {
  if (message.content !== undefined) {
    return message.content;
  }
  return getNestedMessage(message)?.content;
}

function extractBlockText(block: unknown): string {
  if (typeof block === "string") {
    return block;
  }
  if (!block || typeof block !== "object") {
    return "";
  }
  const contentBlock = block as ContentBlock;
  if (typeof contentBlock.text === "string") {
    return contentBlock.text;
  }
  return "";
}

function extractText(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content.map(extractBlockText).filter(Boolean).join("\n");
  }
  return "";
}

function normalizeRole(type: string): "user" | "assistant" | null {
  if (type === "ai" || type === "assistant") {
    return "assistant";
  }
  if (type === "human" || type === "user") {
    return "user";
  }
  return null;
}

function normalizeSingleMessage(raw: unknown): ChatMessage | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }

  const message = raw as MessageLike;
  const role = normalizeRole(getMessageType(message));
  if (!role) {
    return null;
  }

  const content = extractText(getMessageContent(message));

  let createdAt: number | undefined;
  if (typeof message.createdAt === "number") {
    createdAt = message.createdAt;
  } else if (typeof message._creationTime === "number") {
    createdAt = message._creationTime;
  } else {
    const nested = getNestedMessage(message);
    if (typeof nested?.createdAt === "number") {
      createdAt = nested.createdAt;
    } else if (typeof nested?._creationTime === "number") {
      createdAt = nested._creationTime;
    }
  }

  let id: string | undefined;
  if (message.id) {
    id = message.id;
  } else {
    const nested = getNestedMessage(message);
    if (nested?.id) {
      id = nested.id;
    }
  }

  const normalized: ChatMessage = {
    _id: message._id as Id<"uiMessages"> | undefined,
    id: id ?? message.langgraphMessageId,
    role,
    content,
    createdAt: createdAt ?? Date.now(),
  };
  if (message.langgraphMessageId) {
    normalized.langgraphMessageId = message.langgraphMessageId;
  }

  return normalized;
}

export function normalizeMessages(raw: unknown[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  for (const item of raw) {
    const normalized = normalizeSingleMessage(item);
    if (normalized) {
      result.push(normalized);
    }
  }
  return result;
}

export function extractThreadMessages(state: unknown): ChatMessage[] {
  if (!state || typeof state !== "object") {
    return [];
  }
  const messages = (state as ThreadStateLike).values?.messages;
  if (!Array.isArray(messages)) {
    return [];
  }
  return normalizeMessages(messages);
}

export function toAssistantMirrorPayload(
  messages: ChatMessage[],
): AssistantMirrorPayload[] {
  return messages
    .filter((message) => message.role === "assistant" && message.content.trim().length > 0)
    .map((message) => ({
      langgraphMessageId: message.id || message.langgraphMessageId || undefined,
      content: message.content,
      createdAt: message.createdAt,
    }));
}

export function selectLiveAssistantMessage(
  persistedMessages: ChatMessage[],
  streamMessages: ChatMessage[],
): ChatMessage | null {
  const persistedAssistantIds = new Set(
    persistedMessages
      .filter((message) => message.role === "assistant")
      .map((message) => message.id ?? message.langgraphMessageId)
      .filter((id): id is string => Boolean(id)),
  );
  const persistedAssistantContent = new Set(
    persistedMessages
      .filter((message) => message.role === "assistant")
      .map((message) => message.content.trim())
      .filter(Boolean),
  );

  for (let index = streamMessages.length - 1; index >= 0; index -= 1) {
    const message = streamMessages[index];
    if (message?.role !== "assistant" || !message.content.trim()) {
      continue;
    }

    const messageId = message.id ?? message.langgraphMessageId;
    if (messageId && persistedAssistantIds.has(messageId)) {
      continue;
    }

    if (!messageId && persistedAssistantContent.has(message.content.trim())) {
      continue;
    }

    return message;
  }

  return null;
}
