import { getAuthUserId } from "@convex-dev/auth/server";

import type { MutationCtx, QueryCtx } from "../_generated/server";

type ViewerCtx = MutationCtx | QueryCtx;

export async function getViewer(ctx: ViewerCtx) {
  const userId = await getAuthUserId(ctx);
  const identity = await ctx.auth.getUserIdentity();

  if (userId === null || identity === null) {
    throw new Error("Not authenticated");
  }

  const user = await ctx.db.get(userId);
  if (user === null) {
    throw new Error("Authenticated user record is missing");
  }

  return { identity, user, userId };
}

export async function syncViewer(ctx: MutationCtx) {
  const { identity, user, userId } = await getViewer(ctx);
  const now = Date.now();

  const nextFields = {
    name: identity.name ?? user.name,
    email: identity.email ?? user.email,
    image: identity.pictureUrl ?? user.image,
    tokenIdentifier: identity.tokenIdentifier,
    createdAt: user.createdAt ?? now,
    updatedAt: now,
  };

  const changed =
    user.name !== nextFields.name ||
    user.email !== nextFields.email ||
    user.image !== nextFields.image ||
    user.tokenIdentifier !== nextFields.tokenIdentifier ||
    user.createdAt !== nextFields.createdAt;

  if (changed) {
    await ctx.db.patch(userId, nextFields);
    const refreshed = await ctx.db.get(userId);
    if (refreshed === null) {
      throw new Error("Authenticated user record is missing");
    }
    return { identity, user: refreshed, userId };
  }

  return { identity, user, userId };
}
