import { httpRouter } from "convex/server";

import { auth } from "./auth";
import { httpAction } from "./_generated/server";
import { internal } from "./_generated/api";

const http = httpRouter();

auth.addHttpRoutes(http);

http.route({
  path: "/service/turns/finalize",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const expectedToken = process.env.CONVEX_SERVICE_TOKEN;
    const actualToken = request.headers.get("x-rerai-service-token");
    if (!expectedToken || actualToken !== expectedToken) {
      return new Response("Unauthorized", { status: 401 });
    }

    const payload = await request.json();
    const result = await ctx.runMutation(internal.turns.finalize, payload);
    return Response.json(result);
  }),
});

export default http;
