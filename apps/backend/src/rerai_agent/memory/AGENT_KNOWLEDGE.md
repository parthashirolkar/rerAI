# rerAI Agent Knowledge Base — Pune, Maharashtra

## Jurisdiction Context
- **City**: Pune (18.5204°N, 73.8567°E)
- **State**: Maharashtra (code 27)
- **District**: Pune (RERA district code 521, division code 5)
- **Planning Authorities**: PMC (Pune Municipal Corporation), PCMC (Pimpri-Chinchwad), PMRDA (Pune Metropolitan Region Development Authority)
- **Applicable Regulations**: UDCPR 2020 (updated Jan 30, 2025) for all of Maharashtra except MCGM area

## Key Regulation References (UDCPR)
- FSI: General residential ~1.0-2.5 base, with loading for transit, rental housing, etc.
- Setbacks: Front 3.0m+, side/rear vary by plot size and road width
- Parking: Residential 1 ECS per 60 sq.m carpet, commercial per 50 sq.m
- Height: Corresponding to FSI, aviation zone restrictions near Lohegaon airport
- Ground coverage: Max 40-60% depending on plot size

## MahaRERA Portal
- Base URL: https://maharera.maharashtra.gov.in
- Project search: /projects-search-result
- District Pune code: 521
- ~12,000+ pages of projects for Pune district

## Data Sources (Phase 1)
- RERA: MahaRERA portal (scraping)
- Regulations: UDCPR PDF (ChromaDB RAG)

## Data Sources (Phase 2 - COMPLETE)

### Transit Proximity (OpenStreetMap / Overpass API)
- **Endpoint**: https://overpass-api.de/api/interpreter
- **Coverage**: Pune Metro (29+ stations), Indian Railways (6+ stations), Bus stops
- **Tags**: `railway=station+station=subway` (metro), `railway=station+train=yes` (railway), `highway=bus_stop` (bus)
- **Tool**: `check_transit_proximity(lat, lon, radius_km)`
- **Rate limit**: ~2 req/sec, no authentication required

### PMRDA GIS Portal
- **REST API**: https://gis.pmrda.gov.in/api (462 endpoints)
- **WMS Service**: https://gismap.pmrda.gov.in:8443/cgi-bin/IGiS_Ent_service.exe
- **Coverage**: 35+ spatial layers including:
  - Administrative: village, taluka boundaries
  - Infrastructure: metro lines, roads, railways
  - Permissions: building permissions, illegal constructions
  - Environmental: wildlife sanctuaries, private forest overlays
- **Authentication**: None required for read operations
- **Tools**: `query_pmrda_layer()`, `check_development_plan()`

### Data Source Status Summary
| Source | Status | Pune Coverage | Auth Required |
|--------|--------|---------------|---------------|
| OpenStreetMap/Overpass | ACTIVE | Excellent (full) | None |
| PMRDA GIS | ACTIVE | Excellent | None |
| IUDX | DEGRADED | N/A (API down) | Token |
| PMC Open Data | DOWN | N/A | N/A |
| Bhuvan | LIMITED | Manual download only | None |

## Data Sources (Phase 3, planned)
- Environmental: PARIVESH clearance portal, eco-sensitive zone boundaries
