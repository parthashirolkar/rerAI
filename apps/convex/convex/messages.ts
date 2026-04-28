import { paginationOptsValidator } from "convex/server";
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

import {
  buildPreview,
  buildThreadTitle,
  getThreadOwnerOrNull,
  requireThreadOwner,
} from "./lib/threads";

export const listByThread = query({
  args: {
    threadId: v.id("uiThreads"),
    paginationOpts: paginationOptsValidator,
  },
  handler: async (ctx, args) => {
    const { thread } = await getThreadOwnerOrNull(ctx, args.threadId);
    if (thread === null) {
      return {
        page: [],
        isDone: true,
        continueCursor: "",
      };
    }

    return await ctx.db
      .query("uiMessages")
      .withIndex("by_threadId_and_createdAt", (q) => q.eq("threadId", args.threadId))
      .order("desc")
      .paginate(args.paginationOpts);
  },
});

export const appendUserMessage = mutation({
  args: {
    threadId: v.id("uiThreads"),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const { thread, userId } = await requireThreadOwner(ctx, args.threadId);
    const now = Date.now();
    const content = args.content.trim();
    if (!content) {
      throw new Error("Message cannot be empty");
    }

    const messageId = await ctx.db.insert("uiMessages", {
      userId,
      threadId: thread._id,
      role: "user",
      content,
      source: "user_submit",
      createdAt: now,
    });

    await ctx.db.patch(thread._id, {
      title:
        thread.titleSource === "auto" && thread.messageCount === 0
          ? buildThreadTitle(content)
          : thread.title,
      lastMessagePreview: buildPreview(content),
      messageCount: thread.messageCount + 1,
      lastMessageAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(messageId);
  },
});

export const syncAssistantMessages = mutation({
  args: {
    threadId: v.id("uiThreads"),
    messages: v.array(
      v.object({
        langgraphMessageId: v.optional(v.string()),
        content: v.string(),
        createdAt: v.optional(v.number()),
      }),
    ),
  },
  handler: async (ctx, args) => {
    const { thread, userId } = await requireThreadOwner(ctx, args.threadId);
    const orderedMessages = [...args.messages].sort(
      (left, right) => (left.createdAt ?? 0) - (right.createdAt ?? 0),
    );

    let insertedCount = 0;
    let lastCreatedAt = thread.lastMessageAt;
    let lastPreview = thread.lastMessagePreview;

    for (const message of orderedMessages) {
      const content = message.content.trim();
      if (!content) {
        continue;
      }

      if (message.langgraphMessageId) {
        const existing = await ctx.db
          .query("uiMessages")
          .withIndex("by_threadId_and_langgraphMessageId", (q) =>
            q
              .eq("threadId", thread._id)
              .eq("langgraphMessageId", message.langgraphMessageId),
          )
          .unique();
        if (existing !== null) {
          continue;
        }
      }

      const createdAt = message.createdAt ?? Date.now();
      await ctx.db.insert("uiMessages", {
        userId,
        threadId: thread._id,
        role: "assistant",
        content,
        langgraphMessageId: message.langgraphMessageId,
        source: "langgraph_sync",
        createdAt,
      });
      insertedCount += 1;
      lastCreatedAt = createdAt;
      lastPreview = buildPreview(content);
    }

    if (insertedCount > 0) {
      await ctx.db.patch(thread._id, {
        lastMessagePreview: lastPreview,
        messageCount: thread.messageCount + insertedCount,
        lastMessageAt: lastCreatedAt,
        updatedAt: Date.now(),
      });
    }

    return {
      insertedCount,
    };
  },
});
