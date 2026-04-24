import { mutation, query } from "./_generated/server";

import { getViewer, syncViewer } from "./lib/auth";

export const getCurrent = query({
  args: {},
  handler: async (ctx) => {
    try {
      const { identity, user } = await getViewer(ctx);
      return {
        ...user,
        tokenIdentifier: identity.tokenIdentifier,
      };
    } catch {
      return null;
    }
  },
});

export const ensureViewer = mutation({
  args: {},
  handler: async (ctx) => {
    const { identity, user } = await syncViewer(ctx);
    return {
      ...user,
      tokenIdentifier: identity.tokenIdentifier,
    };
  },
});
