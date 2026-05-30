# Frontend Streaming Contract

The web UI treats LangGraph streaming as an integration boundary and mirrors user-visible conversation state into the UI backend instead of treating the stream as the only source of truth. A successful frontend streaming lifecycle creates or selects a UI thread, persists the user message, marks the thread running, submits one resumable LangGraph human message, attaches any returned LangGraph thread ID to the UI thread, displays only genuinely new assistant stream content, mirrors final assistant messages back into the UI backend, and marks the thread idle.

This contract gives the frontend a stable guardrail for diagnosing streaming failures across LangGraph, sub-agents, and Convex persistence. Frontend tests should exercise this lifecycle through the chat ports and stream callbacks so failures can distinguish a broken UI contract from a backend or streaming integration problem.
