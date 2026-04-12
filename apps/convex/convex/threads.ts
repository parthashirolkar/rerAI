import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

import { internal } from "./_generated/api";
import { getViewer } from "./lib/auth";
import { buildPreview, buildThreadTitle, requireThreadOwner } from "./lib/threads";

export const listMine = query({
  args: {},
  handler: async (ctx) => {
    const { userId } = await getViewer(ctx);
    const threads = await ctx.db
      .query("uiThreads")
      .withIndex("by_userId_and_updatedAt", (q) => q.eq("userId", userId))
      .order("desc")
      .take(100);

    return threads.filter((thread) => thread.archivedAt === undefined);
  },
});

export const create = mutation({
  args: {
    title: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const { userId } = await getViewer(ctx);
    const now = Date.now();
    const title = args.title?.trim() || "New chat";
    const id = await ctx.db.insert("uiThreads", {
      userId,
      title,
      titleSource: args.title?.trim() ? "manual" : "auto",
      lastMessagePreview: "",
      messageCount: 0,
      lastMessageAt: now,
      createdAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(id);
  },
});

export const open = query({
  args: {
    threadId: v.id("uiThreads"),
  },
  handler: async (ctx, args) => {
    const { thread } = await requireThreadOwner(ctx, args.threadId);
    return thread;
  },
});

export const rename = mutation({
  args: {
    threadId: v.id("uiThreads"),
    title: v.string(),
  },
  handler: async (ctx, args) => {
    const { thread } = await requireThreadOwner(ctx, args.threadId);
    const title = args.title.trim();
    if (!title) {
      throw new Error("Title cannot be empty");
    }

    await ctx.db.patch(thread._id, {
      title,
      titleSource: "manual",
      updatedAt: Date.now(),
    });
    return await ctx.db.get(thread._id);
  },
});

export const archive = mutation({
  args: {
    threadId: v.id("uiThreads"),
  },
  handler: async (ctx, args) => {
    const { thread } = await requireThreadOwner(ctx, args.threadId);
    await ctx.db.patch(thread._id, {
      archivedAt: Date.now(),
      updatedAt: Date.now(),
    });
    return null;
  },
});

export const remove = mutation({
  args: {
    threadId: v.id("uiThreads"),
  },
  handler: async (ctx, args) => {
    const { thread, userId } = await requireThreadOwner(ctx, args.threadId);

    while (true) {
      const batch = await ctx.db
        .query("uiMessages")
        .withIndex("by_threadId_and_createdAt", (q) => q.eq("threadId", thread._id))
        .take(128);
      if (batch.length === 0) {
        break;
      }
      for (const message of batch) {
        await ctx.db.delete(message._id);
      }
    }

    const runState = await ctx.db
      .query("threadRunState")
      .withIndex("by_threadId", (q) => q.eq("threadId", thread._id))
      .unique();
    if (runState !== null) {
      await ctx.db.delete(runState._id);
    }

    if (thread.langgraphThreadId) {
      await ctx.runMutation(internal.langgraphThreads.forgetThread, {
        userId,
        langgraphThreadId: thread.langgraphThreadId,
      });
    }

    const preferences = await ctx.db
      .query("userPreferences")
      .withIndex("by_userId", (q) => q.eq("userId", userId))
      .unique();
    if (preferences?.lastOpenedThreadId === thread._id) {
      await ctx.db.patch(preferences._id, {
        lastOpenedThreadId: undefined,
        updatedAt: Date.now(),
      });
    }

    await ctx.db.delete(thread._id);
    return null;
  },
});

export const attachLangGraphThread = mutation({
  args: {
    threadId: v.id("uiThreads"),
    langgraphThreadId: v.string(),
  },
  handler: async (ctx, args) => {
    const { thread, userId } = await requireThreadOwner(ctx, args.threadId);
    if (
      thread.langgraphThreadId !== undefined &&
      thread.langgraphThreadId !== args.langgraphThreadId
    ) {
      throw new Error("Thread is already linked to a different LangGraph thread");
    }

    const allowedThread = await ctx.db
      .query("langgraphThreads")
      .withIndex("by_langgraphThreadId", (q) => q.eq("langgraphThreadId", args.langgraphThreadId))
      .unique();
    if (allowedThread === null || allowedThread.userId !== userId) {
      throw new Error("LangGraph thread must be created through the authenticated proxy");
    }

    await ctx.db.patch(thread._id, {
      langgraphThreadId: args.langgraphThreadId,
      updatedAt: Date.now(),
    });
    return await ctx.db.get(thread._id);
  },
});

export const updatePreviewAndCounts = mutation({
  args: {
    threadId: v.id("uiThreads"),
    preview: v.string(),
    lastMessageAt: v.number(),
    messageCountDelta: v.number(),
    titleFromMessage: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const { thread } = await requireThreadOwner(ctx, args.threadId);
    const nextCount = Math.max(0, thread.messageCount + args.messageCountDelta);
    const patch: {
      lastMessagePreview: string;
      lastMessageAt: number;
      messageCount: number;
      updatedAt: number;
      title?: string;
      titleSource?: "auto";
    } = {
      lastMessagePreview: buildPreview(args.preview),
      lastMessageAt: args.lastMessageAt,
      messageCount: nextCount,
      updatedAt: Date.now(),
    };

    if (
      thread.titleSource === "auto" &&
      args.titleFromMessage !== undefined &&
      thread.messageCount === 0
    ) {
      patch.title = buildThreadTitle(args.titleFromMessage);
      patch.titleSource = "auto";
    }

    await ctx.db.patch(thread._id, patch);
    return await ctx.db.get(thread._id);
  },
});
