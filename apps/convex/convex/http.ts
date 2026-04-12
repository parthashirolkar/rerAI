import { httpRouter } from "convex/server";

import { auth } from "./auth";
import { preflight, proxy } from "./langgraphProxy";

const http = httpRouter();

auth.addHttpRoutes(http);

http.route({
  pathPrefix: "/langgraph/",
  method: "OPTIONS",
  handler: preflight,
});

http.route({
  pathPrefix: "/langgraph/",
  method: "GET",
  handler: proxy,
});

http.route({
  pathPrefix: "/langgraph/",
  method: "POST",
  handler: proxy,
});

export default http;
