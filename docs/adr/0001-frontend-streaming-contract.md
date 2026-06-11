# Frontend Streaming Contract

The web UI treats LangGraph streaming as an integration boundary and mirrors user-visible conversation state into the UI backend instead of treating the stream as the only source of truth. A successful frontend streaming lifecycle creates or selects a Conversation, persists the user message, marks the Conversation Turn running, submits one resumable LangGraph human message, attaches any returned LangGraph thread ID to the Conversation, displays only genuinely new assistant stream content, mirrors final assistant messages back into the UI backend, and marks the turn idle.

Selecting a Conversation renders its durable Convex projection immediately. When it contains a Live Turn, the frontend discovers the active Agent Run from durable identifiers and status, then reattaches live delivery asynchronously. Reattachment failure does not block viewing and must never deselect the Conversation.

Navigating away from a Conversation detaches only that browser's live delivery. Its Agent Run continues until it reaches a terminal state or the user explicitly invokes Stop, and selecting the Conversation again automatically attempts to reattach live delivery.

Stop availability follows the durable Live Turn state, not live delivery state. It remains available while reattachment is pending or unavailable and calls the backend cancellation endpoint using the turn's persisted LangGraph thread and run identifiers.

When live delivery cannot reattach while the authoritative turn remains live, the transcript stays visible and presents a non-destructive reconnecting state. Durable Convex projection updates may continue to advance the transcript, Stop remains available, and the UI does not present a failed state unless the authoritative Agent Run fails.

The chat orchestrator is the sole owner of live-delivery reattachment. The LangGraph stream hook's automatic reconnect-on-mount behavior is disabled so it cannot compete with explicit thread switching and run joining.

Joining an Agent Run occurs only after a render in which the stream hook is configured with that run's matching LangGraph thread identifier. Submission and selection set the target thread and desired run, then an effect joins once that thread is current; switching threads and joining a run are never performed sequentially in the same callback.

Every asynchronous reattachment result is scoped to the selected Conversation and the target turn, LangGraph thread, and run identifiers. If any identifier no longer matches when the operation resolves, the frontend discards the stale result.

Browser persistence does not own or restore LangGraph thread and run identity. Reload and selection derive active identifiers from the selected Conversation Turn's Convex projection; browser storage may remember only the selected Conversation for navigation convenience.

Automatic error handling never clears a Conversation's LangGraph thread or run linkage. Linkage is removed only by explicit Conversation deletion or deliberate data repair; authorization failures prevent attachment and present an error without mutating conversation history.

Failed live-delivery reattachment retries automatically with bounded exponential backoff while the Conversation remains selected and its turn remains live. Retries stop on navigation, terminal status, or identifier change; after repeated failures the UI also presents a manual Reconnect action.

Each browser view attaches live delivery only for its selected Conversation. Switching Conversations detaches the previous stream and attaches the newly selected Live Turn when present, while all Agent Runs continue independently and Convex provides durable progress for non-selected Conversations.

If live delivery ends before Convex finalization arrives, provisional streamed content remains visible and the turn presents a finalizing state while its durable status remains running. Terminal Convex projection reconciles that content to canonical Assistant Messages; stream completion alone never marks failure or creates replacement messages.

The frontend reconciles live and Convex Assistant Message content by stable message identity and Message Position. Before finalization it uses the longest prefix-compatible content; if the sources diverge, it prefers the newer backend projection and records the mismatch rather than concatenating incompatible text. Canonical finalization always wins.

Navigating away discards browser-only stream content for that Conversation and relies on the backend Convex projection when returning. The frontend may allow a brief projection flush window before detaching but does not retain cross-Conversation stream buffers.

Returning to a Live Turn renders its latest durable content immediately and presents a subtle catching-up state until live delivery attaches. The UI neither blanks the Assistant Response nor treats projection lag as an error.

Stream interrupt metadata, including a static breakpoint fallback, is non-authoritative and cannot establish Agent Run lifecycle state. Pending graph nodes indicate unfinished work, and transport loss is only local connection state.

Delivery is split into two ordered changes. The first fixes selection, durable turn identity, explicit reattachment ordering, non-destructive stream handling, and Stop behavior. The second adds backend-only provisional Convex projection and removes browser Assistant Message mirroring; the urgent lifecycle fix does not depend on provisional projection.

This contract gives the frontend a stable guardrail for diagnosing streaming failures across LangGraph, sub-agents, and Convex persistence. Frontend tests should exercise this lifecycle through the chat ports and stream callbacks so failures can distinguish a broken UI contract from a backend or streaming integration problem.
