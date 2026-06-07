import { paginationOptsValidator } from "convex/server";
import { internalMutation, query } from "./_generated/server";
import { v } from "convex/values";

import { getThreadOwnerOrNull } from "./lib/threads";
import { buildPreview } from "./lib/threads";

const MAX_ASSISTANT_MESSAGES_PER_TURN = 64;

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

    const turns = await ctx.db
      .query("conversationTurns")
      .withIndex("by_uiThreadId_and_turnPosition", (q) =>
        q.eq("uiThreadId", thread._id),
      )
      .order("desc")
      .paginate(args.paginationOpts);

    const page = await Promise.all(
      turns.page.map(async (turn) => {
        const assistantMessages = await ctx.db
          .query("assistantMessages")
          .withIndex("by_turnId_and_messagePosition", (q) =>
            q.eq("turnId", turn._id),
          )
          .order("asc")
          .take(MAX_ASSISTANT_MESSAGES_PER_TURN);

        return {
          turnId: turn.turnId,
          turnPosition: turn.turnPosition,
          userContent: turn.content,
          status: turn.status,
          assistantMessages: assistantMessages.map((message) => ({
            id: message.messageId,
            langgraphMessageId: message.langgraphMessageId,
            messagePosition: message.messagePosition,
            canonicalContent: message.canonicalContent,
            displayOnlyContent: message.displayOnlyContent,
            createdAt: message.createdAt,
          })),
          createdAt: turn.createdAt,
          errorMessage: turn.errorMessage,
        };
      }),
    );

    return {
      ...turns,
      page,
    };
  },
});

const terminalStatus = v.union(
  v.literal("completed"),
  v.literal("failed"),
  v.literal("cancelled"),
);

export const finalize = internalMutation({
  args: {
    finalizationId: v.string(),
    turnId: v.string(),
    status: terminalStatus,
    errorMessage: v.optional(v.string()),
    assistantMessages: v.array(
      v.object({
        messageId: v.string(),
        langgraphMessageId: v.optional(v.string()),
        messagePosition: v.number(),
        canonicalContent: v.string(),
        displayOnlyContent: v.optional(v.string()),
      }),
    ),
  },
  handler: async (ctx, args) => {
    const turn = await ctx.db
      .query("conversationTurns")
      .withIndex("by_turnId", (q) => q.eq("turnId", args.turnId))
      .unique();
    if (turn === null) {
      throw new Error(`Conversation Turn '${args.turnId}' not found`);
    }
    if (turn.finalizationId === args.finalizationId) {
      return turn;
    }
    if (
      turn.status === "completed" ||
      turn.status === "failed" ||
      turn.status === "cancelled"
    ) {
      return turn;
    }

    const existingMessages = await ctx.db
      .query("assistantMessages")
      .withIndex("by_turnId_and_messagePosition", (q) => q.eq("turnId", turn._id))
      .take(MAX_ASSISTANT_MESSAGES_PER_TURN);
    const incomingIds = new Set(args.assistantMessages.map((message) => message.messageId));
    const existingById = new Map(
      existingMessages.map((message) => [message.messageId, message]),
    );
    const now = Date.now();

    for (const message of args.assistantMessages) {
      const existing = existingById.get(message.messageId);
      if (existing) {
        await ctx.db.patch(existing._id, {
          langgraphMessageId: message.langgraphMessageId,
          messagePosition: message.messagePosition,
          canonicalContent: message.canonicalContent,
          displayOnlyContent: message.displayOnlyContent,
          updatedAt: now,
        });
      } else {
        await ctx.db.insert("assistantMessages", {
          userId: turn.userId,
          uiThreadId: turn.uiThreadId,
          turnId: turn._id,
          messageId: message.messageId,
          langgraphMessageId: message.langgraphMessageId,
          messagePosition: message.messagePosition,
          canonicalContent: message.canonicalContent,
          displayOnlyContent: message.displayOnlyContent,
          createdAt: now,
          updatedAt: now,
        });
      }
    }

    if (args.status === "completed") {
      for (const existing of existingMessages) {
        if (!incomingIds.has(existing.messageId)) {
          await ctx.db.delete(existing._id);
        }
      }
    }

    await ctx.db.patch(turn._id, {
      status: args.status,
      errorMessage: args.errorMessage,
      finalizationId: args.finalizationId,
      terminalAt: now,
      updatedAt: now,
    });

    const thread = await ctx.db.get(turn.uiThreadId);
    if (thread !== null) {
      const lastMessage = args.assistantMessages.at(-1);
      await ctx.db.patch(thread._id, {
        lastMessagePreview: lastMessage
          ? buildPreview(
              `${lastMessage.canonicalContent}${lastMessage.displayOnlyContent ?? ""}`,
            )
          : thread.lastMessagePreview,
        messageCount:
          thread.messageCount +
          args.assistantMessages.filter(
            (message) => !existingById.has(message.messageId),
          ).length,
        lastMessageAt: now,
        updatedAt: now,
      });
    }

    return await ctx.db.get(turn._id);
  },
});
