import type { Doc, Id } from "../_generated/dataModel";
import type { MutationCtx, QueryCtx } from "../_generated/server";

import { getViewer } from "./auth";

type ThreadAccessCtx = MutationCtx | QueryCtx;

export function buildThreadTitle(content: string) {
  const trimmed = content.trim().replace(/\s+/g, " ");
  return trimmed.slice(0, 60) || "New chat";
}

export function buildPreview(content: string) {
  return content.trim().replace(/\s+/g, " ").slice(0, 160);
}

export async function requireThreadOwner(
  ctx: ThreadAccessCtx,
  threadId: Id<"uiThreads">,
) {
  const { user, userId } = await getViewer(ctx);
  const thread = await ctx.db.get(threadId);

  if (thread === null || thread.userId !== userId) {
    throw new Error("Unauthorized");
  }

  return { thread: thread as Doc<"uiThreads">, user, userId };
}

export async function getThreadOwnerOrNull(
  ctx: ThreadAccessCtx,
  threadId: Id<"uiThreads">,
) {
  const { user, userId } = await getViewer(ctx);
  const thread = await ctx.db.get(threadId);

  if (thread === null) {
    return { thread: null, user, userId };
  }

  if (thread.userId !== userId) {
    throw new Error("Unauthorized");
  }

  return { thread: thread as Doc<"uiThreads">, user, userId };
}
