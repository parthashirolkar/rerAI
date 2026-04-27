import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";
import { authTables } from "@convex-dev/auth/server";

export default defineSchema({
  ...authTables,
  users: defineTable({
    name: v.optional(v.string()),
    image: v.optional(v.string()),
    email: v.optional(v.string()),
    emailVerificationTime: v.optional(v.number()),
    phone: v.optional(v.string()),
    phoneVerificationTime: v.optional(v.number()),
    isAnonymous: v.optional(v.boolean()),
    tokenIdentifier: v.optional(v.string()),
    createdAt: v.optional(v.number()),
    updatedAt: v.optional(v.number()),
  })
    .index("email", ["email"])
    .index("phone", ["phone"])
    .index("by_tokenIdentifier", ["tokenIdentifier"]),
  userPreferences: defineTable({
    userId: v.id("users"),
    sidebarWidth: v.number(),
    sidebarOpen: v.boolean(),
    lastOpenedThreadId: v.optional(v.id("uiThreads")),
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index("by_userId", ["userId"]),
  uiThreads: defineTable({
    userId: v.id("users"),
    title: v.string(),
    titleSource: v.union(v.literal("auto"), v.literal("manual")),
    langgraphThreadId: v.optional(v.string()),
    lastMessagePreview: v.string(),
    messageCount: v.number(),
    lastMessageAt: v.number(),
    createdAt: v.number(),
    updatedAt: v.number(),
    archivedAt: v.optional(v.number()),
  })
    .index("by_userId_and_updatedAt", ["userId", "updatedAt"])
    .index("by_userId_and_createdAt", ["userId", "createdAt"])
    .index("by_langgraphThreadId", ["langgraphThreadId"]),
  uiMessages: defineTable({
    userId: v.id("users"),
    threadId: v.id("uiThreads"),
    role: v.union(v.literal("user"), v.literal("assistant"), v.literal("system")),
    content: v.string(),
    langgraphMessageId: v.optional(v.string()),
    source: v.union(v.literal("user_submit"), v.literal("langgraph_sync"), v.literal("system")),
    createdAt: v.number(),
  })
    .index("by_threadId_and_createdAt", ["threadId", "createdAt"])
    .index("by_threadId_and_langgraphMessageId", ["threadId", "langgraphMessageId"])
    .index("by_userId_and_createdAt", ["userId", "createdAt"]),
  threadRunState: defineTable({
    threadId: v.id("uiThreads"),
    userId: v.id("users"),
    langgraphRunId: v.optional(v.string()),
    status: v.union(
      v.literal("idle"),
      v.literal("running"),
      v.literal("interrupted"),
      v.literal("error"),
    ),
    errorMessage: v.optional(v.string()),
    updatedAt: v.number(),
  })
    .index("by_threadId", ["threadId"])
    .index("by_userId_and_updatedAt", ["userId", "updatedAt"]),
});
