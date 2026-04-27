import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

import { getViewer } from "./lib/auth";

export const viewer = query({
  args: {},
  handler: async (ctx) => {
    const { identity, user, userId } = await getViewer(ctx);
    return {
      userId,
      tokenIdentifier: identity.tokenIdentifier,
      name: user.name,
      email: user.email,
    };
  },
});

export const getThreadByLangGraphThreadId = query({
  args: {
    langgraphThreadId: v.string(),
  },
  handler: async (ctx, args) => {
    const { userId } = await getViewer(ctx);
    const matches = await ctx.db
      .query("uiThreads")
      .withIndex("by_langgraphThreadId", (q) => q.eq("langgraphThreadId", args.langgraphThreadId))
      .take(16);
    const thread = matches.find((candidate) => candidate.userId === userId);

    if (thread === undefined || thread.archivedAt !== undefined) {
      return null;
    }

    return thread;
  },
});

export const attachLangGraphThread = mutation({
  args: {
    threadId: v.id("uiThreads"),
    langgraphThreadId: v.string(),
  },
  handler: async (ctx, args) => {
    const { userId } = await getViewer(ctx);
    const thread = await ctx.db.get(args.threadId);
    if (thread === null || thread.userId !== userId) {
      throw new Error("Unauthorized");
    }
    if (
      thread.langgraphThreadId !== undefined &&
      thread.langgraphThreadId !== args.langgraphThreadId
    ) {
      throw new Error("Thread is already linked to a different LangGraph thread");
    }

    const existing = await ctx.db
      .query("uiThreads")
      .withIndex("by_langgraphThreadId", (q) => q.eq("langgraphThreadId", args.langgraphThreadId))
      .take(16);
    if (existing.some((candidate) => candidate._id !== thread._id)) {
      throw new Error("LangGraph thread is already linked to another conversation");
    }

    await ctx.db.patch(thread._id, {
      langgraphThreadId: args.langgraphThreadId,
      updatedAt: Date.now(),
    });
    return await ctx.db.get(thread._id);
  },
});
