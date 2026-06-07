# Durable Turn Finalization

The backend run orchestrator owns Assistant Message persistence and terminal Conversation Turn status because LangGraph runs may continue after the browser disconnects. Backend-to-Convex finalization uses idempotent service-authenticated mutations and a durable backend outbox with retry, so transient Convex failures cannot leave a completed, failed, or cancelled run missing from the user-visible transcript.

Each finalization is projected through one atomic Convex mutation. The mutation reconciles the complete final Assistant Message set, removes obsolete provisional messages, retains any applicable display-only partial content, and applies the immutable terminal turn status together.

Canonical Assistant Message content and display-only partial continuation are stored separately in the Convex projection. They may render within one Assistant Message block, but display-only content is structurally excluded from canonical agent history.

When failure or cancellation leaves only uncheckpointed visible text, Convex retains a display-only Assistant Message record with its streamed identity and Message Position. When a canonical prefix exists, the display-only continuation is attached to that same projected message block.

The backend orchestrator assigns each Assistant Message its Message Position in first-seen order from the durable run-event log. The frontend consumes those positions, and finalization preserves them; qualifying messages discovered only in canonical final state receive subsequent positions.

Each Conversation Turn is correlated with a frontend-generated stable HumanMessage identifier and `turnId`, both persisted by the backend before LangGraph execution begins. Finalization uses that HumanMessage as the canonical history boundary for the turn.

Turn creation and run creation are coordinated through one backend submission endpoint keyed idempotently by `turnId`. The backend ensures the pending Convex turn exists, durably creates the LangGraph run, and returns stable run and thread identifiers; repeated submission of the same `turnId` returns the same run rather than creating another.

Stop uses an explicit authenticated, idempotent backend cancellation endpoint for the active run identifier. Closing an SSE subscription does not cancel agent work; the cancellation endpoint records intent, cancels active execution, waits for terminal acknowledgement, and returns the actual immutable terminal outcome when completion wins the race.

On backend startup, persisted runs left in the running state without active execution are terminalized as failed and projected from their available checkpoints and durable events. Automatic execution resumption is outside this decision.

Convex transcript pagination is turn-shaped and uses an explicit turn ordering key and turn-level cursor. Each page returns complete Conversation Turns with their user request and ordered Assistant Messages; pagination never splits a turn or derives conversational order from timestamps.

Each backend run attempt has a stable finalization identifier. Convex records the applied identifier so repeated delivery of the same outbox payload is a no-op and cannot duplicate messages, change Message Positions, or refresh thread recency.

Failed turns show an inline failure state and re-enable the composer. The frontend does not offer an in-place retry action; a subsequent user submission begins a new Conversation Turn.
