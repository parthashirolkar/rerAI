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

export const ensureTurn = mutation({
  args: {
    uiThreadId: v.id("uiThreads"),
    turnId: v.string(),
    humanMessageId: v.string(),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const { userId } = await getViewer(ctx);
    const thread = await ctx.db.get(args.uiThreadId);
    if (thread === null || thread.userId !== userId || thread.archivedAt !== undefined) {
      throw new Error("Unauthorized");
    }

    const content = args.content.trim();
    if (!content) {
      throw new Error("Message cannot be empty");
    }

    const existing = await ctx.db
      .query("conversationTurns")
      .withIndex("by_turnId", (q) => q.eq("turnId", args.turnId))
      .unique();
    if (existing !== null) {
      return existing;
    }

    const latestTurn = await ctx.db
      .query("conversationTurns")
      .withIndex("by_uiThreadId_and_turnPosition", (q) =>
        q.eq("uiThreadId", thread._id),
      )
      .order("desc")
      .first();
    const now = Date.now();
    const turnId = await ctx.db.insert("conversationTurns", {
      userId,
      uiThreadId: thread._id,
      turnId: args.turnId,
      humanMessageId: args.humanMessageId,
      content,
      turnPosition: (latestTurn?.turnPosition ?? -1) + 1,
      status: "pending",
      createdAt: now,
      updatedAt: now,
    });

    await ctx.db.patch(thread._id, {
      title:
        thread.titleSource === "auto" && thread.messageCount === 0
          ? args.content.trim().replace(/\s+/g, " ").slice(0, 60)
          : thread.title,
      lastMessagePreview: content.slice(0, 160),
      messageCount: thread.messageCount + 1,
      lastMessageAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(turnId);
  },
});

export const markTurnRunning = mutation({
  args: {
    turnId: v.string(),
    langgraphThreadId: v.string(),
    langgraphRunId: v.string(),
  },
  handler: async (ctx, args) => {
    const { userId } = await getViewer(ctx);
    const turn = await ctx.db
      .query("conversationTurns")
      .withIndex("by_turnId", (q) => q.eq("turnId", args.turnId))
      .unique();
    if (turn === null || turn.userId !== userId) {
      throw new Error("Unauthorized");
    }
    if (
      turn.langgraphRunId !== undefined &&
      turn.langgraphRunId !== args.langgraphRunId
    ) {
      throw new Error("Conversation Turn is already linked to another run");
    }
    if (
      turn.status === "completed" ||
      turn.status === "failed" ||
      turn.status === "cancelled"
    ) {
      return turn;
    }

    const thread = await ctx.db.get(turn.uiThreadId);
    if (thread === null || thread.userId !== userId) {
      throw new Error("Unauthorized");
    }

    const now = Date.now();
    await ctx.db.patch(turn._id, {
      status: "running",
      langgraphThreadId: args.langgraphThreadId,
      langgraphRunId: args.langgraphRunId,
      updatedAt: now,
    });
    if (thread.langgraphThreadId === undefined) {
      await ctx.db.patch(thread._id, {
        langgraphThreadId: args.langgraphThreadId,
        updatedAt: now,
      });
    } else if (thread.langgraphThreadId !== args.langgraphThreadId) {
      throw new Error("Thread is already linked to another LangGraph thread");
    }
    return await ctx.db.get(turn._id);
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
