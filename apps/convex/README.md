# rerAI Convex app

This app is the public/authenticated boundary for rerAI.

It owns:
- Google sign-in through Convex Auth
- user identity and viewer records
- app state such as threads, messages, and preferences
- the authenticated `/langgraph` proxy to the Railway backend

## Local Development

```bash
bun install
bun run dev
```

Local connection settings live in [apps/convex/.env.local](/home/partha/git-repos/rerAI/apps/convex/.env.local).

## Production Environment Variables

Set these on the Convex deployment:

- `LANGGRAPH_INTERNAL_API_URL`
- `LANGGRAPH_INTERNAL_SHARED_SECRET`
- `CLIENT_ORIGINS`
- `AUTH_GOOGLE_ID`
- `AUTH_GOOGLE_SECRET`

What they do:
- `LANGGRAPH_INTERNAL_API_URL`: the public Railway backend URL that Convex proxies requests to
- `LANGGRAPH_INTERNAL_SHARED_SECRET`: shared secret forwarded by [convex/langgraphProxy.ts](/home/partha/git-repos/rerAI/apps/convex/convex/langgraphProxy.ts)
- `CLIENT_ORIGINS`: comma-separated allowed frontend origins for the proxy CORS layer
- `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET`: Google OAuth credentials used by Convex Auth

## Google OAuth

Google auth is configured in [convex/auth.ts](/home/partha/git-repos/rerAI/apps/convex/convex/auth.ts) via the `Google` provider.

The Google Cloud Console redirect URI must be:

```text
https://<your-convex-site>.convex.site/api/auth/callback/google
```

For the current dev deployment in this repo, that shape is:

```text
https://loyal-shark-354.eu-west-1.convex.site/api/auth/callback/google
```

If you later deploy a separate production Convex deployment, add that production Convex Site callback URL to the same Google OAuth client.

## Deploy

```bash
bun run deploy
```
