---
name: permit-feasibility
description: Full permit feasibility assessment for a plot in Pune. Gathers data from RERA, regulations, GIS, and land records to produce a structured report.
trigger: When the user asks about permit feasibility, building permissions, or development potential for a specific plot.
---

# Permit Feasibility Assessment

## Workflow

1. **Plan** — Use `write_todos` to create a task list covering all pillars
2. **GIS Check** — Delegate to `gis-analyst` to determine:
   - Transit proximity (metro, railway, bus)
   - PMRDA jurisdiction (village, taluka boundaries)
   - Development plan context (nearby permissions, metro lines)
   - Environmental zones (wildlife sanctuaries, forest overlays)
3. **Title Check** — Delegate to `title-verifier` to fetch and analyze 7/12 extract:
   - Current ownership and shares
   - Land classification (agricultural/NA/ghairan)
   - Area on record vs claimed
   - Encumbrances and liabilities
4. **RERA Check** — Delegate to `rera-analyst` to check developer/project compliance history
5. **Regulatory Check** — Delegate to `regulatory-checker` to determine FSI, setbacks, parking requirements
6. **Synthesize** — Compile findings into a structured report

## Output Format

```markdown
# Permit Feasibility Report: [Plot/Address]

## 1. Plot Identification
- Address / Survey Number / Coordinates
- Planning Authority (PMC/PCMC/PMRDA)
- Village / Taluka / District (from GIS)

## 2. Title & Ownership (from title-verifier)
- Current owners and their shares
- Land classification (Agricultural / NA / Gairan)
- Encumbrances / liens noted in 7/12
- Area on record vs claimed

## 3. Spatial Context (from gis-analyst)
- DP zoning designation
- Metro/railway proximity
- Bus connectivity
- Nearby building permissions
- Environmental zone status (wildlife sanctuary, forest overlay)

## 4. Regulatory Assessment (from regulatory-checker)
- Applicable FSI (base + loaded)
- Permissible Height
- Setback Requirements
- Parking Norms
- Ground Coverage Limit
- Any special Development Control rules

## 5. RERA Compliance (from rera-analyst)
- Nearby registered projects
- Developer track record
- Any disputes or complaints

## 6. Summary & Recommendations
- Development potential (estimated built-up area = FSI × plot area)
- Key constraints and risks identified
- Required approvals and clearances
- Suggested next steps
```

## Important Notes

- **GIS data** is for preliminary screening only. Verify with official PMRDA/PMC records for final decisions.
- **7/12 extract** data is per Mahabhulekh portal disclaimer: for informational purposes, not for legal use.
- **Transit proximity** calculations use OpenStreetMap data which may not reflect real-time service availability.
- Always recommend the user verify critical findings with official authorities before making decisions.
