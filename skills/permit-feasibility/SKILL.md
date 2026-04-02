---
name: permit-feasibility
description: Full permit feasibility assessment for a plot in Pune. Gathers data from RERA, regulations, GIS, and land records to produce a structured report.
trigger: When the user asks about permit feasibility, building permissions, or development potential for a specific plot.
---

# Permit Feasibility Assessment

## Workflow

1. **Plan** — Use `write_todos` to create a task list covering all pillars
2. **RERA Check** — Delegate to `rera-analyst` to check developer/project compliance history
3. **Regulatory Check** — Delegate to `regulatory-checker` to determine FSI, setbacks, parking requirements
4. **Synthesize** — Compile findings into a structured report

## Output Format

```markdown
# Permit Feasibility Report: [Plot/Address]

## 1. Plot Identification
- Address / Survey Number / Coordinates
- Planning Authority (PMC/PCMC/PMRDA)

## 2. Regulatory Assessment
- Applicable FSI
- Permissible Height
- Setback Requirements
- Parking Norms
- Ground Coverage Limit

## 3. RERA Compliance
- Nearby registered projects
- Developer compliance history

## 4. Summary & Recommendations
- Development potential (estimated built-up area)
- Key constraints
- Required clearances
```
