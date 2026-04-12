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
  threadId: string,
) {
  const { user, userId } = await getViewer(ctx);
  const thread = await ctx.db.get(threadId as never);

  if (thread === null || thread.userId !== userId) {
    throw new Error("Unauthorized");
  }

  return { thread, user, userId };
}
