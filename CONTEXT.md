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

## Flagged Ambiguities

- "plot" was used to mean both **Land Parcel** and **RERA Project**; resolved: use **Development Site** for the user-facing lookup target, and distinguish land-record evidence from RERA evidence.
- "web search result" was used to mean both retrieved page text and source-backed **Evidence**; resolved: the agent should receive structured **Evidence**, not raw retrieved text.
- "web search" was used to describe both a provider call and a domain workflow; resolved: call the domain workflow **Development Site Lookup**.
- "source" was used without authority level; resolved: distinguish **Authoritative Source** from **Corroborating Source**.
- Parsed user query fields were at risk of being treated as facts; resolved: call them **Search Hints** until confirmed by **Evidence**.
- Ambiguous identifiers were at risk of triggering speculative searches; resolved: the agent should ask follow-up questions and form a **Research Brief** before lookup.
