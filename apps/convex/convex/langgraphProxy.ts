import type { Id } from "./_generated/dataModel";
import { api, internal } from "./_generated/api";
import { httpAction } from "./_generated/server";

const LANGGRAPH_PROXY_PREFIX = "/langgraph";
const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "last-event-id"];
const RESERVED_THREAD_SEGMENTS = new Set(["search"]);

function getAllowedOrigin(origin: string | null) {
  const configuredOrigins = (process.env.CLIENT_ORIGINS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);

  if (origin === null) {
    return configuredOrigins[0] ?? "*";
  }
  if (configuredOrigins.length === 0) {
    return origin;
  }
  return configuredOrigins.includes(origin) ? origin : null;
}

function corsHeaders(origin: string) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Headers": "Authorization, Content-Type, Last-Event-ID",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    Vary: "Origin",
  };
}

function jsonError(message: string, status: number, origin: string) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: {
      "content-type": "application/json",
      ...corsHeaders(origin),
    },
  });
}

function resolveForwardPath(request: Request) {
  const url = new URL(request.url);
  if (!url.pathname.startsWith(`${LANGGRAPH_PROXY_PREFIX}/`)) {
    throw new Error("Unsupported LangGraph proxy path");
  }
  return `${url.pathname.slice(LANGGRAPH_PROXY_PREFIX.length)}${url.search}`;
}

function extractThreadId(pathname: string) {
  const match = pathname.match(/^\/threads\/([^/]+)(?:\/|$)/);
  if (!match) {
    return null;
  }
  const threadId = decodeURIComponent(match[1]);
  return RESERVED_THREAD_SEGMENTS.has(threadId) ? null : threadId;
}

function readThreadIdFromJsonBody(pathname: string, contentType: string | null, bodyText: string) {
  if (pathname !== "/runs/stream" || !contentType?.includes("application/json")) {
    return null;
  }

  try {
    const parsed = JSON.parse(bodyText) as { thread_id?: unknown };
    return typeof parsed.thread_id === "string" ? parsed.thread_id : null;
  } catch {
    return null;
  }
}

function createForwardHeaders(request: Request) {
  const headers = new Headers();
  for (const headerName of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(headerName);
    if (value) {
      headers.set(headerName, value);
    }
  }
  return headers;
}

export const preflight = httpAction(async (_ctx, request) => {
  const allowedOrigin = getAllowedOrigin(request.headers.get("origin"));
  if (allowedOrigin === null) {
    return new Response(null, { status: 403 });
  }

  return new Response(null, {
    status: 204,
    headers: corsHeaders(allowedOrigin),
  });
});

export const proxy = httpAction(async (ctx, request) => {
  const allowedOrigin = getAllowedOrigin(request.headers.get("origin"));
  if (allowedOrigin === null) {
    return new Response("Origin not allowed", {
      status: 403,
      headers: request.headers.get("origin")
        ? {
            Vary: "Origin",
          }
        : undefined,
    });
  }

  const internalApiUrl = process.env.LANGGRAPH_INTERNAL_API_URL?.trim();
  if (!internalApiUrl) {
    return jsonError("Missing LANGGRAPH_INTERNAL_API_URL", 500, allowedOrigin);
  }

  const identity = await ctx.auth.getUserIdentity();
  if (identity === null) {
    return jsonError("Not authenticated", 401, allowedOrigin);
  }

  await ctx.runMutation(api.users.ensureViewer, {});
  const userId: Id<"users"> = await ctx.runQuery(
    internal.langgraphThreads.getUserIdByTokenIdentifier,
    {
      tokenIdentifier: identity.tokenIdentifier,
    },
  );

  const forwardPath = resolveForwardPath(request);
  const pathname = forwardPath.split("?")[0] ?? forwardPath;
  const bodyBytes = request.method === "GET" ? null : await request.arrayBuffer();
  const contentType = request.headers.get("content-type");
  const bodyText = bodyBytes === null ? "" : new TextDecoder().decode(bodyBytes);

  const threadIdFromPath = extractThreadId(pathname);
  const threadIdFromBody = readThreadIdFromJsonBody(pathname, contentType, bodyText);
  const threadId = threadIdFromPath ?? threadIdFromBody;
  if (threadId) {
    await ctx.runMutation(internal.langgraphThreads.authorizeThreadAccess, {
      userId,
      langgraphThreadId: threadId,
    });
  }

  const response = await fetch(new URL(forwardPath, internalApiUrl), {
    method: request.method,
    headers: createForwardHeaders(request),
    body: bodyBytes,
  });

  if (request.method === "POST" && pathname === "/threads" && response.ok) {
    const payload = (await response.clone().json().catch(() => null)) as
      | { thread_id?: unknown }
      | null;
    if (typeof payload?.thread_id === "string") {
      await ctx.runMutation(internal.langgraphThreads.registerThread, {
        userId,
        langgraphThreadId: payload.thread_id,
      });
    }
  }

  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(corsHeaders(allowedOrigin))) {
    headers.set(name, value);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
});
