import type { MutationCtx, QueryCtx } from "./_generated/server";
import { internalMutation, internalQuery } from "./_generated/server";
import { v } from "convex/values";

async function findRegisteredThread(ctx: MutationCtx | QueryCtx, langgraphThreadId: string) {
  return await ctx.db
    .query("langgraphThreads")
    .withIndex("by_langgraphThreadId", (q) => q.eq("langgraphThreadId", langgraphThreadId))
    .unique();
}

export const getUserIdByTokenIdentifier = internalQuery({
  args: {
    tokenIdentifier: v.string(),
  },
  handler: async (ctx, args) => {
    const user = await ctx.db
      .query("users")
      .withIndex("by_tokenIdentifier", (q) => q.eq("tokenIdentifier", args.tokenIdentifier))
      .unique();

    if (user === null) {
      throw new Error("Authenticated user record is missing");
    }

    return user._id;
  },
});

export const authorizeThreadAccess = internalMutation({
  args: {
    userId: v.id("users"),
    langgraphThreadId: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await findRegisteredThread(ctx, args.langgraphThreadId);
    if (existing !== null) {
      if (existing.userId !== args.userId) {
        throw new Error("Unauthorized LangGraph thread access");
      }
      return null;
    }

    const linkedThreads = await ctx.db
      .query("uiThreads")
      .withIndex("by_langgraphThreadId", (q) => q.eq("langgraphThreadId", args.langgraphThreadId))
      .take(16);
    const ownsLinkedThread = linkedThreads.some((thread) => thread.userId === args.userId);
    if (!ownsLinkedThread) {
      throw new Error("Unauthorized LangGraph thread access");
    }

    await ctx.db.insert("langgraphThreads", {
      userId: args.userId,
      langgraphThreadId: args.langgraphThreadId,
      createdAt: Date.now(),
    });
    return null;
  },
});

export const registerThread = internalMutation({
  args: {
    userId: v.id("users"),
    langgraphThreadId: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await findRegisteredThread(ctx, args.langgraphThreadId);
    if (existing !== null) {
      if (existing.userId !== args.userId) {
        throw new Error("LangGraph thread is already owned by another user");
      }
      return null;
    }

    await ctx.db.insert("langgraphThreads", {
      userId: args.userId,
      langgraphThreadId: args.langgraphThreadId,
      createdAt: Date.now(),
    });
    return null;
  },
});

export const forgetThread = internalMutation({
  args: {
    userId: v.id("users"),
    langgraphThreadId: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await findRegisteredThread(ctx, args.langgraphThreadId);
    if (existing === null) {
      return null;
    }
    if (existing.userId !== args.userId) {
      throw new Error("LangGraph thread is owned by another user");
    }

    await ctx.db.delete(existing._id);
    return null;
  },
});
