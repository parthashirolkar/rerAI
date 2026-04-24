type MessageLike = {
  content?: unknown;
  id?: string;
  _id?: string;
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

function getMessageType(message: MessageLike) {
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

function getMessageContent(message: MessageLike) {
  if (message.content !== undefined) {
    return message.content;
  }

  return getNestedMessage(message)?.content;
}

function getMessageId(message: MessageLike) {
  if (message.id) {
    return message.id;
  }

  const nested = getNestedMessage(message);
  if (nested?.id) {
    return nested.id;
  }

  if (message._id) {
    return message._id;
  }

  return null;
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

export function extractMessageText(message: unknown): string {
  if (!message || typeof message !== "object") {
    return "";
  }

  const content = getMessageContent(message as MessageLike);
  if (typeof content === "string") {
    return content;
  }

  if (Array.isArray(content)) {
    return content.map(extractBlockText).filter(Boolean).join("\n");
  }

  return "";
}

export function isAssistantMessage(message: unknown) {
  if (!message || typeof message !== "object") {
    return false;
  }

  const type = getMessageType(message as MessageLike);
  return type === "ai" || type === "assistant";
}

export function isUserMessage(message: unknown) {
  if (!message || typeof message !== "object") {
    return false;
  }

  const type = getMessageType(message as MessageLike);
  return type === "human" || type === "user";
}

export function getMessageKey(message: unknown, index: number) {
  if (message && typeof message === "object") {
    const value = getMessageId(message as MessageLike);
    if (value) {
      return value;
    }
  }

  return `message-${index}`;
}

export function getMessageTimestamp(message: unknown) {
  if (!message || typeof message !== "object") {
    return null;
  }

  const candidate = message as MessageLike;
  if (typeof candidate.createdAt === "number") {
    return candidate.createdAt;
  }

  if (typeof candidate._creationTime === "number") {
    return candidate._creationTime;
  }

  const nested = getNestedMessage(candidate);
  if (typeof nested?.createdAt === "number") {
    return nested.createdAt;
  }

  if (typeof nested?._creationTime === "number") {
    return nested._creationTime;
  }

  return null;
}

export function extractThreadStateMessages(state: unknown): unknown[] {
  if (!state || typeof state !== "object") {
    return [];
  }

  const messages = (state as ThreadStateLike).values?.messages;
  if (!Array.isArray(messages)) {
    return [];
  }

  return messages.filter((message) => isUserMessage(message) || isAssistantMessage(message));
}
