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

## Data Sources (Phase 2, planned)
- GIS: IUDX API, Bhuvan WMS/WFS, PMC Open Data Portal
- Land Records: Mahabhulekh 7/12 extracts via Playwright

## Data Sources (Phase 3, planned)
- Environmental: PARIVESH clearance portal, eco-sensitive zone boundaries
