import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  uiThreads: defineTable({
    title: v.string(),
    langgraphThreadId: v.optional(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  }),
  uiMessages: defineTable({
    threadId: v.id("uiThreads"),
    role: v.union(v.literal("user"), v.literal("assistant"), v.literal("system")),
    content: v.string(),
    createdAt: v.number(),
  }).index("by_thread", ["threadId"]),
});
