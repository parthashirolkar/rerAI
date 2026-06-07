# rerAI

rerAI supports preliminary permitting analysis for development sites in Pune, Maharashtra by linking land records, RERA records, GIS context, and regulations.

## Language

**Development Site**:
A real-world site being evaluated for development, identified through land-record and project-registration evidence.
_Avoid_: plot, property, project site

**Land Parcel**:
A land-record unit identified by administrative location and survey or gat number.
_Avoid_: plot when referring to a 7/12 record

**RERA Project**:
A registered MahaRERA project or phase associated with one or more development sites or land parcels.
_Avoid_: plot when referring to a RERA registration

**Evidence**:
A source-backed fact or candidate fact used to assess a development site.
_Avoid_: raw search result, text dump

**Development Site Lookup**:
A domain workflow that discovers and expands evidence for a development site from land-record and RERA sources.
_Avoid_: web search when referring to the user-facing workflow

**Search Hint**:
A candidate identifier interpreted from a user query for retrieval, not yet established as evidence.
_Avoid_: evidence, fact

**Research Brief**:
The clarified user request containing enough location and identifier detail to begin a development site lookup.
_Avoid_: vague plot query, speculative lookup

**Authoritative Source**:
An official government source that can establish RERA or land-record evidence for a development site.
_Avoid_: treating corroborating sources as authoritative

**Corroborating Source**:
A non-official source that can help discover candidate identifiers but cannot by itself establish high-confidence evidence.
_Avoid_: authoritative source

**Conversation Turn**:
A user request together with every user-visible assistant message produced before the next user request.
_Avoid_: treating each assistant message as a separate turn

**Assistant Message**:
A non-empty textual communication emitted by the top-level rerAI agent within a conversation turn.
_Avoid_: AIMessage when speaking about product behavior

**Assistant Response**:
The single user-visible region that presents all assistant messages belonging to one conversation turn.
_Avoid_: rendering each assistant message as a separate chat bubble

**Message Position**:
The stable ordinal assigned to a message within its conversation turn.
_Avoid_: deriving conversational order from timestamps

**Cancelled Turn**:
A conversation turn whose active agent work was explicitly stopped while preserving its visible messages and conversation history.
_Avoid_: interrupted turn

**Failed Turn**:
A conversation turn whose agent work ended unsuccessfully while preserving its visible messages and canonical conversation history.
_Avoid_: treating failure as deletion

**Stop**:
The user action that cancels the active agent work without deleting its conversation turn or thread.
_Avoid_: steer, interrupt

## Relationships

- A **Development Site** may be supported by evidence from one or more **Land Parcels**
- A **Development Site** may be associated with zero or more **RERA Projects**
- A **RERA Project** may span one or more **Land Parcels**
- A **Land Parcel** may be associated with zero or more **RERA Projects**
- **Evidence** must cite the source it came from
- A **Development Site Lookup** may use multiple searches or fetches internally but should return structured **Evidence**
- A **Search Hint** may guide retrieval but must not be reported as established fact without source-backed **Evidence**
- A **Development Site Lookup** should begin from a **Research Brief**, not an ambiguous identifier the system tries to reinterpret
- A **Research Brief** must include a district, one locality or administrative hint, and one labeled site or project identifier
- High-confidence **Evidence** requires an **Authoritative Source**
- A **Corroborating Source** may support discovery but must not establish a high-confidence match by itself
- A **Conversation Turn** begins with exactly one user request and may contain one or more **Assistant Messages**
- Tool activity and delegated work may contribute to a **Conversation Turn** without appearing as **Assistant Messages**
- Tool-call-only messages and internal subagent messages are not **Assistant Messages**
- A **Conversation Turn** presents its **Assistant Messages** in order within exactly one **Assistant Response**
- A completed **Conversation Turn** includes every qualifying **Assistant Message** from canonical agent history, even when live delivery omitted one
- Canonical agent history determines the final content of each **Assistant Message** without changing its identity or **Message Position**
- A completed **Conversation Turn** excludes provisional visible messages that are absent from canonical agent history
- Every message has one **Message Position** that remains unchanged while streaming, persisting, and reloading
- A **Cancelled Turn** remains part of the conversation and does not invalidate its thread
- **Stop** preserves canonical checkpointed **Assistant Message** content, while any uncheckpointed visible continuation remains display-only
- A **Cancelled Turn** retains its display-only continuation across reloads and identifies it as stopped
- Continuing after a **Cancelled Turn** begins a new **Conversation Turn** rather than reopening the cancelled one
- A **Failed Turn** preserves canonical checkpointed **Assistant Messages**, retains any uncheckpointed visible continuation across reloads as display-only content, and identifies it as failed

## Example Dialogue

> **Dev:** "When the user gives a plot number, should we return the matching RERA project?"
> **Domain expert:** "Treat it as a **Development Site** lookup. First identify the **Land Parcel**, then return candidate **RERA Projects** as linked evidence with confidence."

> **Dev:** "Should the agent inspect the full web search text?"
> **Domain expert:** "No. Return only **Evidence** and source citations unless a debug path is explicitly requested."

> **Dev:** "Should the agent perform the initial search and then decide follow-up searches?"
> **Domain expert:** "No. Use a **Development Site Lookup** so discovery, follow-up retrieval, and reduction happen behind one domain-level call."

> **Dev:** "If the user says 'Plot 15, Jamtha, Pune', can we treat Jamtha and 15 as facts?"
> **Domain expert:** "No. Treat them as **Search Hints** until source-backed **Evidence** confirms the land parcel or RERA project."

> **Dev:** "If the user only gives '15 near Pune', should the lookup tool search survey, gat, CTS, and plot variants?"
> **Domain expert:** "No. The agent should first turn the request into a **Research Brief** by asking follow-up questions."

> **Dev:** "Is 'Plot 15, Jamtha, Pune' enough for lookup?"
> **Domain expert:** "Yes. It has a district, locality, and labeled identifier. '15 Pune' is not enough."

> **Dev:** "Can a developer brochure prove that a RERA project matches a land parcel?"
> **Domain expert:** "No. It can provide corroborating evidence, but high confidence requires an **Authoritative Source**."

> **Dev:** "If rerAI delegates research and reports progress before its final answer, is that several turns?"
> **Domain expert:** "No. It is one **Conversation Turn** containing multiple **Assistant Messages**; hidden tool activity and delegated work do not create turns."

> **Dev:** "Should each progress update from rerAI appear as another assistant bubble?"
> **Domain expert:** "No. Present every **Assistant Message** as an ordered block within the turn's single **Assistant Response**."

> **Dev:** "Should a persisted assistant message replace its streamed version in the transcript?"
> **Domain expert:** "No. It is the same **Assistant Message** at the same **Message Position**; persistence changes durability, not conversational identity."

> **Dev:** "What if the final answer never arrived in the live stream?"
> **Domain expert:** "Include it when the completed **Conversation Turn** is reconciled with canonical agent history; live delivery does not determine which **Assistant Messages** belong to the turn."

> **Dev:** "What if streamed text differs from the completed message in canonical agent history?"
> **Domain expert:** "Use the canonical text while preserving the **Assistant Message** identity and **Message Position**."

> **Dev:** "What if a streamed message is absent from canonical agent history when the turn completes?"
> **Domain expert:** "Exclude it from the completed **Conversation Turn**; live delivery is provisional until canonical reconciliation."

> **Dev:** "Does stopping a long-running assessment discard the conversation?"
> **Domain expert:** "No. Stop the active work, retain any visible messages as a **Cancelled Turn**, and allow a new turn in the same conversation."

> **Dev:** "Should partial text from a stopped generation be injected into the next agent request?"
> **Domain expert:** "No. **Stop** preserves it for the user to read, but the next turn continues from canonical checkpointed state plus the new user request."

> **Dev:** "What if part of a stopped assistant message was already checkpointed?"
> **Domain expert:** "Keep the checkpointed content as canonical conversation history and retain only its uncheckpointed visible continuation as display-only content."

> **Dev:** "Should unfinished text disappear after reloading a stopped conversation?"
> **Domain expert:** "No. A **Cancelled Turn** keeps the display-only continuation readable and marks it as stopped."

> **Dev:** "Does asking rerAI to continue reopen the stopped turn?"
> **Domain expert:** "No. The **Cancelled Turn** remains unchanged, and continuing begins a new **Conversation Turn**."

> **Dev:** "Should unfinished text disappear when agent work fails?"
> **Domain expert:** "No. A **Failed Turn** keeps uncheckpointed visible content readable and marks it as failed, but that content does not enter canonical conversation history."

> **Dev:** "Does failure erase assistant messages that were already checkpointed?"
> **Domain expert:** "No. A **Failed Turn** preserves checkpointed **Assistant Messages** as canonical conversation history and keeps only their uncheckpointed continuation display-only."

## Flagged Ambiguities

- "plot" was used to mean both **Land Parcel** and **RERA Project**; resolved: use **Development Site** for the user-facing lookup target, and distinguish land-record evidence from RERA evidence.
- "web search result" was used to mean both retrieved page text and source-backed **Evidence**; resolved: the agent should receive structured **Evidence**, not raw retrieved text.
- "web search" was used to describe both a provider call and a domain workflow; resolved: call the domain workflow **Development Site Lookup**.
- "source" was used without authority level; resolved: distinguish **Authoritative Source** from **Corroborating Source**.
- Parsed user query fields were at risk of being treated as facts; resolved: call them **Search Hints** until confirmed by **Evidence**.
- Ambiguous identifiers were at risk of triggering speculative searches; resolved: the agent should ask follow-up questions and form a **Research Brief** before lookup.
- "message" was used to mean both framework events and user-visible chat content; resolved: use **Assistant Message** for visible rerAI communication and **Conversation Turn** for its causal grouping with a user request.
- Message timestamps were used as conversational ordering keys; resolved: use **Conversation Turn** membership and **Message Position**, keeping timestamps as metadata only.
- "interrupted" implied a human-in-the-loop pause that rerAI does not support; resolved: explicit user-initiated stopping produces a **Cancelled Turn**.
