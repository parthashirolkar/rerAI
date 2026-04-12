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
};

type ContentBlock = {
  text?: string;
  type?: string;
};

function getMessageType(message: MessageLike) {
  return (
    message.getType?.() ??
    message._getType?.() ??
    message.role ??
    message.type ??
    "unknown"
  ).toLowerCase();
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

  const content = (message as MessageLike).content;
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
  if (message && typeof message === "object" && "id" in message) {
    const value = (message as MessageLike).id;
    if (value) {
      return value;
    }
  }

  if (message && typeof message === "object" && "_id" in message) {
    const value = (message as MessageLike)._id;
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

  return null;
}
