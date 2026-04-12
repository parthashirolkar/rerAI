import type { MutationCtx } from "./_generated/server";
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

import { requireThreadOwner } from "./lib/threads";

async function upsertRunState(
  ctx: MutationCtx,
  threadId: string,
  userId: string,
  patch: {
    langgraphRunId?: string;
    status: "idle" | "running" | "interrupted" | "error";
    errorMessage?: string;
  },
) {
  const existing = await ctx.db
    .query("threadRunState")
    .withIndex("by_threadId", (q) => q.eq("threadId", threadId as never))
    .unique();

  const next = {
    userId: userId as never,
    threadId: threadId as never,
    updatedAt: Date.now(),
    ...patch,
  };

  if (existing !== null) {
    await ctx.db.patch(existing._id, next);
    return await ctx.db.get(existing._id);
  }

  const id = await ctx.db.insert("threadRunState", next);
  return await ctx.db.get(id);
}

export const getForThread = query({
  args: {
    threadId: v.id("uiThreads"),
  },
  handler: async (ctx, args) => {
    await requireThreadOwner(ctx, args.threadId);
    return await ctx.db
      .query("threadRunState")
      .withIndex("by_threadId", (q) => q.eq("threadId", args.threadId))
      .unique();
  },
});

export const setRunning = mutation({
  args: {
    threadId: v.id("uiThreads"),
    langgraphRunId: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const { userId } = await requireThreadOwner(ctx, args.threadId);
    return await upsertRunState(ctx, args.threadId, userId, {
      langgraphRunId: args.langgraphRunId,
      status: "running",
      errorMessage: undefined,
    });
  },
});

export const setInterrupted = mutation({
  args: {
    threadId: v.id("uiThreads"),
  },
  handler: async (ctx, args) => {
    const { userId } = await requireThreadOwner(ctx, args.threadId);
    return await upsertRunState(ctx, args.threadId, userId, {
      status: "interrupted",
      errorMessage: undefined,
    });
  },
});

export const setError = mutation({
  args: {
    threadId: v.id("uiThreads"),
    errorMessage: v.string(),
  },
  handler: async (ctx, args) => {
    const { userId } = await requireThreadOwner(ctx, args.threadId);
    return await upsertRunState(ctx, args.threadId, userId, {
      status: "error",
      errorMessage: args.errorMessage.trim() || "Unknown error",
    });
  },
});

export const setIdle = mutation({
  args: {
    threadId: v.id("uiThreads"),
  },
  handler: async (ctx, args) => {
    const { userId } = await requireThreadOwner(ctx, args.threadId);
    return await upsertRunState(ctx, args.threadId, userId, {
      status: "idle",
      errorMessage: undefined,
    });
  },
});
