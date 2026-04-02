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

## Phase 2 — Spatial & Land Records ✅ COMPLETE

### 2A: GIS Spatial Tools (`tools/gis_tools.py`)

**Status:** ✅ Implemented

**Purpose:** Given coordinates or an address, determine plot-level spatial context — transit proximity, jurisdiction boundaries, development zones, environmental overlays.

**Data sources implemented:**

| Source | What it provides | Access method | Status |
|---|---|---|---|
| **OpenStreetMap** | Metro stations, railway stations, bus stops | Overpass API (`overpass-api.de`) | ✅ ACTIVE |
| **PMRDA GIS** | Village/taluka boundaries, building permissions, metro lines, environmental zones | REST API + WMS at `gis.pmrda.gov.in` | ✅ ACTIVE |
| IUDX (India Urban Data Exchange) | City-level sensor data, water supply, traffic | Public REST API | ❌ DEGRADED |
| Bhuvan (ISRO's geo-platform) | WMS/WFS map tiles — land use, contour, flood hazard | Public WMS endpoints | ⚠️ LIMITED |
| PMC Open Data | Development plan zones, DP remarks, building permissions | `opendata.punecorporation.org` | ❌ DOWN |

**Tools implemented:**

- ✅ `check_transit_proximity(lat, lon, radius_km) -> str` — Find nearest metro station, railway station, bus stops using OSM Overpass
- ✅ `query_pmrda_layer(layer_name, lat, lon, radius_m) -> str` — Query specific PMRDA GIS layer for features
- ✅ `check_development_plan(lat, lon) -> str` — Comprehensive spatial context (jurisdiction, transit, permissions, environmental zones)

**Deferred:**
- `check_flood_zone()` — Bhuvan WMS requires undocumented `map` parameter paths
- `check_infrastructure()` — IUDX/PMC APIs unavailable

**Subagent: `gis-analyst`**
- Model: `nvidia/nemotron-3-nano-30b-a3b:free` via OpenRouter
- Tools: `check_transit_proximity`, `query_pmrda_layer`, `check_development_plan`
- System prompt: Spatial analyst for Pune plots, returns structured location assessment

### 2B: Land Records Tools (`tools/land_records_tools.py`)

**Status:** ✅ Implemented

**Purpose:** Given a survey/gat number and village name, extract 7/12 (Satbara) and Property Card data — ownership, land classification, area, encumbrances.

**Data source:** Mahabhulekh (`mahabhulekh.maharashtra.gov.in`)
- Publicly accessible — no API key needed
- Requires Playwright for navigating the multi-step form (Division → District → Taluka → Village → Survey No.)
- Returns 7/12 extract with: owner names, land area, classification (agri/NA/ghairan), rights, liabilities

**Tools implemented:**

- ✅ `fetch_7_12_extract(district, taluka, village, survey_no) -> str` — Playwright automation to navigate Mahabhulekh and extract 7/12 data
- ✅ `fetch_property_card(district, taluka, village, survey_no) -> str` — Returns guidance for property cards (typically managed by municipalities, not revenue dept)

**Technical notes:**
- Playwright automation handles popup windows and cascading dropdowns
- BeautifulSoup parsing for HTML table extraction
- Local caching of dropdown values to reduce portal load
- Retry logic with exponential backoff for portal unreliability
- Output in Marathi (Sakal Marathi Normal font)

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
