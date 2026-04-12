import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

import { getViewer } from "./lib/auth";

const DEFAULT_SIDEBAR_WIDTH = 256;
const DEFAULT_SIDEBAR_OPEN = true;

export const getMine = query({
  args: {},
  handler: async (ctx) => {
    const { userId } = await getViewer(ctx);
    const preferences = await ctx.db
      .query("userPreferences")
      .withIndex("by_userId", (q) => q.eq("userId", userId))
      .unique();

    if (preferences !== null) {
      return preferences;
    }

    return {
      _id: null,
      _creationTime: Date.now(),
      userId,
      sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
      sidebarOpen: DEFAULT_SIDEBAR_OPEN,
      lastOpenedThreadId: undefined,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
  },
});

export const updateMine = mutation({
  args: {
    sidebarWidth: v.optional(v.number()),
    sidebarOpen: v.optional(v.boolean()),
    lastOpenedThreadId: v.optional(v.union(v.id("uiThreads"), v.null())),
  },
  handler: async (ctx, args) => {
    const { userId } = await getViewer(ctx);
    const now = Date.now();
    const existing = await ctx.db
      .query("userPreferences")
      .withIndex("by_userId", (q) => q.eq("userId", userId))
      .unique();

    const patch = {
      sidebarWidth: args.sidebarWidth ?? existing?.sidebarWidth ?? DEFAULT_SIDEBAR_WIDTH,
      sidebarOpen: args.sidebarOpen ?? existing?.sidebarOpen ?? DEFAULT_SIDEBAR_OPEN,
      lastOpenedThreadId:
        args.lastOpenedThreadId === null
          ? undefined
          : args.lastOpenedThreadId ?? existing?.lastOpenedThreadId,
      updatedAt: now,
    };

    if (existing !== null) {
      await ctx.db.patch(existing._id, patch);
      return await ctx.db.get(existing._id);
    }

    const id = await ctx.db.insert("userPreferences", {
      userId,
      createdAt: now,
      ...patch,
    });
    return await ctx.db.get(id);
  },
});
