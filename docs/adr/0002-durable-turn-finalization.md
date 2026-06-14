# Durable Turn Finalization

The backend run orchestrator owns Assistant Message persistence and terminal Conversation Turn status because LangGraph runs may continue after the browser disconnects. Backend-to-Convex finalization uses idempotent service-authenticated mutations and a durable backend outbox with retry, so transient Convex failures cannot leave a completed, failed, or cancelled run missing from the user-visible transcript.

The backend run store is authoritative for Agent Run lifecycle state. Convex owns the durable user-visible projection of that state, while browser persistence and live stream state are non-authoritative connection state. The frontend must not infer that an Agent Run is failed, cancelled, or completed solely from stream state.

Every non-terminal Conversation Turn projection exposes both its LangGraph thread identifier, which identifies workflow state, and its LangGraph run identifier, which identifies the active Agent Run. Terminal turns retain both identifiers for correlation and diagnostics, but the frontend treats them as actionable only while a turn is live.

Conversation Turn lifecycle status uses pending, running, completed, failed, and cancelled. There is no interrupted status; Stop produces a Cancelled Turn.

Convex projects Agent Run lifecycle state on `conversationTurns`, not in a separate Conversation-level run-state record. Each projected turn carries its own lifecycle status and run identifiers; Conversation state is derived from its turns.

The turn-shaped `turns.listByThread` projection returns each turn's LangGraph thread and run identifiers together with its transcript and lifecycle status, avoiding a separate reconnect-state query.

Pending and running are non-terminal and both block another submission in the same Conversation. A pending turn is durably accepted but does not yet have attachable run identity and presents a starting state; a running turn is attachable only when both LangGraph identifiers are present, and Stop is available only once a cancellable run identifier exists.

A pending turn that cannot establish an Agent Run is terminalized as failed by backend reconciliation rather than remaining pending indefinitely. Startup and periodic recovery preserve the Conversation and project a clear run-start failure.

Stale-pending detection uses a configurable backend-owned lease or timeout. Frontend timers do not determine lifecycle transitions, and no fixed recovery duration is part of the product contract.

A running turn without both LangGraph identifiers is an invalid projection and is reconciled to failed by the backend. Until correction, the frontend presents unavailable run state, remains non-destructive, does not attempt attachment, and continues to block another submission in that Conversation.

A timed-out submission is never retried automatically because resubmission could create unintended Agent Runs and token usage. The frontend reconciles the original client-generated `turnId` without resubmitting, presents an unknown submission state until durable state confirms the outcome, and exposes a small manual Try again action beneath the user message only after the original submission is confirmed failed or absent.

Try again creates a new Conversation Turn with a new `turnId` and copied user content. The failed original turn remains unchanged and visible; retry never reopens or overwrites it.

Try again is available for failed turns and for submissions confirmed absent after an unknown outcome. It is not offered for Cancelled Turns, which reflect deliberate user intent.

A Conversation has at most one pending or running Conversation Turn. While it has a Live Turn, the composer rejects new submissions and presents Stop instead of Send; different Conversations may have concurrent Agent Runs.

After Stop is requested, the turn remains live and presents a stopping state until the backend response or Convex projection establishes the terminal outcome. Completion may win the race; the frontend presents a Cancelled Turn only when cancellation is authoritative and never marks cancellation optimistically.

Deleting a Conversation with a Live Turn first requests cancellation and waits for an authoritative terminal outcome before deleting the Conversation projection. During this operation the UI presents a stopping-and-deleting state; immediate deletion must not orphan an active backend Agent Run.

If cancellation cannot be confirmed, deletion fails and leaves the Conversation intact with an actionable error. The normal UI offers retrying deletion or keeping the Conversation and does not force-delete an active or uncertain Agent Run.

Each finalization is projected through one atomic Convex mutation. The mutation reconciles the complete final Assistant Message set, removes obsolete provisional messages, retains any applicable display-only partial content, and applies the immutable terminal turn status together.

Canonical Assistant Message content and display-only partial continuation are stored separately in the Convex projection. They may render within one Assistant Message block, but display-only content is structurally excluded from canonical agent history.

During a Live Turn, provisional Assistant Message content is mirrored durably through idempotent updates keyed by turn, message identity, and Message Position. This preserves visible progress across navigation and reload while keeping provisional content structurally separate from canonical history until backend finalization.

Provisional persistence updates are coalesced at a bounded interval rather than written per token, with flushes on message boundaries, navigation, stream end, Stop, and feasible page lifecycle events. Backend finalization remains authoritative.

The backend orchestrator is the sole writer of provisional and final Assistant Message projections from its durable run-event stream. Browser-to-Convex Assistant Message mirroring is removed; the browser only renders live stream events together with the Convex projection.

When failure or cancellation leaves only uncheckpointed visible text, Convex retains a display-only Assistant Message record with its streamed identity and Message Position. When a canonical prefix exists, the display-only continuation is attached to that same projected message block.

The backend orchestrator assigns each Assistant Message its Message Position in first-seen order from the durable run-event log. The frontend consumes those positions, and finalization preserves them; qualifying messages discovered only in canonical final state receive subsequent positions.

Each Conversation Turn is correlated with a frontend-generated stable HumanMessage identifier and `turnId`, both persisted by the backend before LangGraph execution begins. Finalization uses that HumanMessage as the canonical history boundary for the turn.

Turn creation and run creation are coordinated through one backend submission endpoint keyed idempotently by `turnId`. The backend ensures the pending Convex turn exists, durably creates the LangGraph run, and returns stable run and thread identifiers; repeated submission of the same `turnId` returns the same run rather than creating another.

Stop uses an explicit authenticated, idempotent backend cancellation endpoint for the active run identifier. Closing an SSE subscription does not cancel agent work; the cancellation endpoint records intent, cancels active execution, waits for terminal acknowledgement, and returns the actual immutable terminal outcome when completion wins the race.

On backend startup, persisted runs left in the running state without active execution are terminalized as failed and projected from their available checkpoints and durable events. Automatic execution resumption is outside this decision.

Convex transcript pagination is turn-shaped and uses an explicit turn ordering key and turn-level cursor. Each page returns complete Conversation Turns with their user request and ordered Assistant Messages; pagination never splits a turn or derives conversational order from timestamps.

Each backend run attempt has a stable finalization identifier. Convex records the applied identifier so repeated delivery of the same outbox payload is a no-op and cannot duplicate messages, change Message Positions, or refresh thread recency.

Failed turns show an inline failure state and re-enable the composer. The frontend does not offer an in-place retry action; a subsequent user submission begins a new Conversation Turn.
