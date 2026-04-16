# rerAI web app

This app is a Vite-built React SPA. It talks to Convex for authentication and app data, and Convex proxies LangGraph-compatible requests to the Railway backend.

## Local Development

```bash
bun install
bun run dev
```

Required frontend env vars:

- `VITE_CONVEX_URL`
- `VITE_CONVEX_SITE_URL`

See [apps/web/.env.example](/home/partha/git-repos/rerAI/apps/web/.env.example).

## Recommended Hosting

Use Cloudflare Pages as the default free host for this app.

Recommended Cloudflare Pages settings:

- Root directory: `apps/web`
- Build command: `bun run build`
- Output directory: `dist`

Production env vars:

- `VITE_CONVEX_URL=https://<your-convex-deployment>.convex.cloud`
- `VITE_CONVEX_SITE_URL=https://<your-convex-deployment>.convex.site`

This frontend does not need:

- `AUTH_GOOGLE_ID`
- `AUTH_GOOGLE_SECRET`
- `LANGGRAPH_INTERNAL_SHARED_SECRET`

Those belong to the Convex deployment, not the browser app.

## SPA Routing

The app includes [public/_redirects](/home/partha/git-repos/rerAI/apps/web/public/_redirects) so static hosts that support redirect files can serve `index.html` for unknown client-side routes.
