# rerAI — Roadmap & Phase Specifications

## Completed: Phase 1 — Foundation (RERA + Regulatory RAG + Orchestrator)

**Commit:** `f52ac60` on `master`

**What was built:**
- `main.py` — REPL orchestrator using `deepagents.create_deep_agent()`
- `tools/config.py` — Shared LLM (OpenRouter/Qwen) + embedding (Ollama/embeddinggemma) config
- `tools/rera_tools.py` — `search_rera_projects()` + `get_rera_project_details()` `@tool` functions (scrapes MahaRERA portal)
- `tools/regulatory_tools.py` — UDCPR PDF ingestion into ChromaDB (576 pages → 1625 chunks) + `query_udcpr()` RAG tool
- `subagents/definitions.py` — `rera-analyst` + `regulatory-checker` subagent configs
- `memory/AGENT_KNOWLEDGE.md` — Pune jurisdiction context loaded at agent runtime
- `skills/permit-feasibility/SKILL.md` — Permit assessment workflow skill scaffold

**Models:**
- Orchestrator: `qwen/qwen3.6-plus:free` via OpenRouter
- Subagents: `nvidia/nemotron-3-nano-30b-a3b:free` via OpenRouter
- Embeddings: `embeddinggemma:latest` via Ollama (langchain-ollama)

**Data ingested:**
- UDCPR 2025 PDF (updated to 30 Jan 2025, 576 pages) from DTP Maharashtra

---

## Phase 2 — Spatial & Land Records

### 2A: GIS Spatial Tools (`tools/gis_tools.py`)

**Purpose:** Given coordinates or an address, determine plot-level spatial context — land use zoning, flood zones, transit proximity, infrastructure availability.

**Data sources to explore:**

| Source | What it provides | Access method |
|---|---|---|
| **IUDX** (India Urban Data Exchange) | City-level sensor data, water supply, traffic, drainage | Public REST API at `data.iudx.org.in` |
| **Bhuvan** (ISRO's geo-platform) | WMS/WFS map tiles — land use, contour, flood hazard, watershed | Public WMS endpoints at `bhuvan.nrsc.gov.in` |
| **PMC Open Data** (Pune Municipal Corporation) | Development plan zones, DP remarks, building permissions | `opendata.punecorporation.org` or scraping `pmc.gov.in` |
| **OpenStreetMap** | Roads, transit stations, landmarks, building footprints | Overpass API (`overpass-api.de`) |
| **PMRDA** | Regional plan zones, metro corridor planning | `pmrda.gov.in` (scraping) |

**Tools to build:**

- `query_pmc_development_plan(lat, lon) -> str` — Given coordinates, return the DP zoning (residential, commercial, industrial, etc.) and any special reservations
- `check_flood_zone(lat, lon) -> str` — Check if plot falls in a flood-prone area (Bhuvan flood hazard layer or PMC drainage data)
- `check_transit_proximity(lat, lon, radius_km) -> str` — Find nearest metro station, bus depot, railway station using OSM Overpass
- `check_infrastructure(lat, lon) -> str` — Water supply, sewage, road width from IUDX/PMC data

**Subagent: `gis-analyst`**
- Model: `nvidia/nemotron-3-nano-30b-a3b:free` via OpenRouter
- Tools: All GIS tools above
- System prompt: Spatial analyst for Pune plots, returns structured location assessment

### 2B: Land Records Tools (`tools/land_records_tools.py`)

**Purpose:** Given a survey/gat number and village name, extract 7/12 (Satbara) and Property Card data — ownership, land classification, area, encumbrances.

**Data source:** Mahabhulekh (`mahabhulekh.maharashtra.gov.in` / `bhulekh.mahabhubblekh.com`)
- Publicly accessible — no API key needed
- Requires Playwright for navigating the multi-step form (State → District → Taluka → Village → Survey No.)
- Returns 7/12 extract with: owner names, land area, classification (agri/NA/ghairan), rights, liabilities

**Tools to build:**

- `fetch_7_12_extract(district: str, taluka: str, village: str, survey_no: str) -> str` — Playwright automation to navigate Mahabhulekh and extract 7/12 data
- `fetch_property_card(district: str, taluka: str, village: str, survey_no: str) -> str` — Extract property card (Malmatta Patrak) data

**Technical notes:**
- Playwright is already a dependency
- Mahabhulekh uses dynamic dropdowns (select district → loads talukas → loads villages)
- Rate limiting and polite delays needed
- May need OCR if the extract is rendered as an image

**Subagent: `title-verifier`**
- Model: `nvidia/nemotron-3-nano-30b-a3b:free` via OpenRouter
- Tools: `fetch_7_12_extract`, `fetch_property_card`
- System prompt: Land title verification specialist, identifies ownership, classification, encumbrances

---

## Phase 3 — Environmental & Synthesis

### 3A: Environmental Tools (`tools/environmental_tools.py`)

**Purpose:** Check environmental clearances, eco-sensitive zone proximity, CRZ applicability, and EIA requirements for a given plot.

**Data sources to explore:**

| Source | What it provides | Access method |
|---|---|---|
| **PARIVESH** (MoEFCC portal) | Environmental clearance status, EIA reports, forest clearances | `parivesh.nic.in` (scraping or API if available) |
| **ESZ notifications** (MoEFCC) | Eco-Sensitive Zone boundaries around national parks, wildlife sanctuaries | Gazette notifications + Bhuvan boundary layers |
| **CRZ maps** | Coastal Regulation Zone boundaries (less relevant for Pune, but needed for Maharashtra-wide coverage) | NCSCM coastal zone maps |
| **Maharashtra PCB** | Pollution control consent status, NOC for construction | `mpcb.gov.in` |

**Tools to build:**

- `check_ecozones(lat, lon) -> str` — Check proximity to eco-sensitive zones (Bhuvan WMS layer for ESZ boundaries)
- `check_parivesh_clearances(project_name: str, district: str) -> str` — Search PARIVESH for environmental clearances in the area
- `check_eia_applicability(plot_area: float, project_type: str) -> str` — Determine if EIA is required based on project category and size (Schedule I/II of EIA notification 2006)

**Subagent: `environmental-checker`**
- Model: `nvidia/nemotron-3-nano-30b-a3b:free` via OpenRouter
- Tools: All environmental tools above
- System prompt: Environmental compliance specialist for Maharashtra construction projects

### 3B: Full Permit Feasibility Report (Synthesis)

**Purpose:** Combine all pillar outputs into a single structured report.

**What to build:**
- Flesh out `skills/permit-feasibility/SKILL.md` with the full multi-step workflow
- Add report generation logic — the orchestrator calls all subagents in parallel, then synthesizes

**Report structure:**

```
# Permit Feasibility Report: [Plot/Address]

## 1. Plot Identification
- Address / Survey Number / Coordinates
- Planning Authority (PMC/PCMC/PMRDA)
- Area (sq.m)

## 2. Title & Ownership (from title-verifier)
- Current owners
- Land classification (Agricultural / NA / Gairan)
- Encumbrances / liens
- Area on record vs claimed

## 3. Regulatory Assessment (from regulatory-checker)
- Applicable FSI (base + loaded)
- Permissible height
- Setback requirements
- Parking norms
- Ground coverage limit
- Any special Development Control rules

## 4. Spatial Context (from gis-analyst)
- DP zoning designation
- Flood zone status
- Transit proximity
- Infrastructure availability

## 5. RERA Compliance (from rera-analyst)
- Nearby registered projects
- Developer track record
- Any disputes or complaints

## 6. Environmental Clearance (from environmental-checker)
- EIA applicability
- Eco-sensitive zone proximity
- Required environmental NOCs

## 7. Summary & Recommendations
- Estimated developable area (FSI × plot area)
- Key constraints and risks
- Required approvals and clearances
- Suggested next steps
```

---

## Future Considerations (Post Phase 3)

- **Web frontend** — Streamlit or React dashboard for non-technical users
- **PDF report generation** — Auto-generate downloadable feasibility reports
- **Multi-city support** — Extend beyond Pune to other Maharashtra cities
- **Real-time integration** — PMC building permission status API if it becomes available
- **Agent memory persistence** — Cross-session memory using deepagents CompositeBackend + LangGraph Store
- **Guardrails** — Input validation, confidence scoring, hallucination checks on regulation citations
