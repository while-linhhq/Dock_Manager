---
name: lucid-diagram
description: Draw diagrams (ERD, flowchart, architecture) on Lucidchart using the Lucid MCP server. Use when the user mentions drawing, creating, or editing diagrams on Lucidchart, or asks to visualize database schemas, system architecture, or any diagram. Prioritizes saved ERD styling config (blue header, alternate rows, Crow's Foot notation).
---

# Lucidchart Diagram via MCP

## MCP Tools

| Tool | When to use |
|------|-------------|
| `fetch` | Get existing document (shapes, lines, IDs) |
| `lucid_create_diagram_from_specification` | Create new diagram with shapes + relationships in one shot |
| `lucid_edit_item` | Move/resize existing shapes |
| `lucid_add_block` | Add a single shape to existing doc |
| `lucid_add_line` | Add a connector line (no Crow's Foot support) |

**Critical**: `lucid_add_line` does NOT support Crow's Foot notation. For ERDs with relationship arrows, always include lines inside `lucid_create_diagram_from_specification`.

**Payload limit**: `lucid_create_diagram_from_specification` has a **53KB max**. If exceeded, reduce cell-level styling (apply only to odd rows, skip even rows).

---

## Saved ERD Styling Config

Always apply these defaults unless the user specifies otherwise:

```json
{
  "header": {
    "fill": "#5B9BD5",
    "fontColor": "#FFFFFF",
    "bold": true
  },
  "alternateRows": {
    "oddRow": "#F2F2F2",
    "evenRow": "#FFFFFF"
  },
  "shape": "DefaultTableBlock",
  "columns": 3,
  "columnHeaders": ["key", "field", "type"]
}
```

### ERD Relationship Arrow Styles (Crow's Foot)

| Cardinality | endpoint style |
|-------------|----------------|
| Exactly one (parent) | `CFN ERD One Arrow` |
| Zero or more (child) | `CFN ERD Zero Or More Arrow` |
| One or more | `CFN ERD One Or More Arrow` |
| Zero or one | `CFN ERD Zero Or One Arrow` |

---

## ERD Shape Specification Template

```json
{
  "id": "table_name",
  "class": "DefaultTableBlock",
  "boundingBox": { "x": 0, "y": 0, "w": 280, "h": 200 },
  "style": {
    "table": {
      "headerRow": { "fill": "#5B9BD5", "fontColor": "#FFFFFF", "bold": true }
    },
    "cells": [
      { "row": 1, "col": 0, "fill": "#F2F2F2" },
      { "row": 1, "col": 1, "fill": "#F2F2F2" },
      { "row": 1, "col": 2, "fill": "#F2F2F2" }
    ]
  },
  "textAreas": [
    { "label": "Cell_0,0", "text": "table_name" },
    { "label": "Cell_0,1", "text": "" },
    { "label": "Cell_0,2", "text": "" },
    { "label": "Cell_1,0", "text": "PK" },
    { "label": "Cell_1,1", "text": "id" },
    { "label": "Cell_1,2", "text": "SERIAL" }
  ]
}
```

Cell key constraints: `PK`, `FK`, `U`, `NN`, `U,NN` — leave empty string for no constraint.

---

## ERD Layout Principles

Arrange tables to minimize line crossings. Follow data-flow: **left → right, top → bottom**.

Recommended zone layout:

```
[Auth zone]     [Vessel/Config zone]   [Activity zone]   [Finance zone]
roles           vessel_types           detections         orders
users           vessels                detection_media    invoices ── payments
audit_logs      fee_configs            port_logs          invoice_items
export_logs     port_configs
```

- Parent tables: **above** or **left** of child tables
- Tables with many FK targets (e.g. `users`): place in top-left, accept long lines
- "Join" tables (e.g. `invoices` connected to 3+ parents): place in **center** of the diagram
- Gap between tables: 60–80px horizontal, 50–60px vertical

---

## Workflow: Create New ERD

1. **Fetch** existing doc if editing: `fetch(document_id)`
2. Plan zones and assign (x, y) per table
3. Build `lucid_create_diagram_from_specification` payload:
   - shapes array with `DefaultTableBlock` + styling
   - lines array with Crow's Foot endpoints
4. If payload > 53KB: remove even-row fill cells (use `#FFFFFF` default)
5. After creation, rearrange with `lucid_edit_item` if needed

## Workflow: Edit Layout Only

```python
# Move each shape by calling lucid_edit_item in parallel
lucid_edit_item(document_id, item_id, x, y, width, height)
```

Batch all 15+ calls in a single message for speed.

---

## Project Document

Current port management ERD:
- **Document ID**: `6c1d0b12-8765-4682-a1df-97e55187c523`
- **Edit URL**: https://lucid.app/lucidchart/6c1d0b12-8765-4682-a1df-97e55187c523/edit
- **Tables**: 15 tables, 19 relationships
