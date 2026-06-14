---
name: google-sheets-editor
description: Update existing Google Sheets tabs from local data, database query results, or generated rows while preserving sheet structure, gid targeting, table metadata, banding, filters, dimensions, and verification evidence. Use when writing to a Google Sheet, copying the format of another tab, or fixing Sheets styling that depends on real tables rather than plain cell formatting.
---

# Google Sheets Editor

Use this skill to safely update an existing Google Sheet tab and keep its visible and structural formatting intact.

## Local Auth

Use the existing local OAuth setup:

- Python venv: `/Users/idah/.local/share/google-sheets-client-venv`
- OAuth client: `~/.config/gspread/credentials.json`
- Authorized token: `~/.config/gspread/authorized_user.json`

Run Google Sheets scripts with:

```bash
/Users/idah/.local/share/google-sheets-client-venv/bin/python
```

Prefer `gspread` for value reads/writes and worksheet discovery. Use raw Sheets API `batchUpdate` through `client.http_client.request(...)` for tables, banding, filters, and dimensions.

## Safety Rules

- Never print OAuth tokens, DB passwords, or spreadsheet credentials.
- If the user gives a `gid`, resolve the worksheet by `worksheet.id`; do not rely on title alone.
- Modify only the requested spreadsheet and tab.
- For database-backed sheet data, follow the relevant database safety rules first. For prod data, run read-only SQL unless the user explicitly authorizes writes.
- Before overwriting tab contents, identify the spreadsheet ID, target tab title, target `gid`, and expected row/column shape.
- Treat table-range blank rows as unsafe, not as existing data. `get_all_values()` may return blank rows preserved by a Google Sheets table range; do not use those blank rows as the full rewrite source of truth.
- For append-only updates, write only the append range (for example `A5:H6`) whenever possible. Do not rewrite the whole table range just to append rows.
- Before any full-range rewrite, verify the key identifier column has the expected non-empty row count. If identifier rows are unexpectedly blank or missing, stop and reconstruct/confirm the rows instead of preserving the blanks.

## Core Workflow

1. Open the spreadsheet by key.
2. Resolve source and target worksheets by `gid`.
3. Read current tab metadata with `spreadsheets.get`:
   - `tables`
   - `bandedRanges`
   - `basicFilter`
   - `filterViews`
   - sheet properties and grid size
4. Generate rows from the requested source.
5. Write the smallest intended range:
   - append-only changes should update only the new rows
   - full rewrites require a non-empty identifier-row count check first
6. Reapply the sheet structure:
   - freeze header row
   - wrap text
   - vertical align top
   - row height
   - column widths
   - `bandedRanges`
   - a real `tables` object when the source tab uses Google Sheets Tables
7. Read back the tab and verify:
   - header match
   - row count
   - key identifiers or sample values
   - table metadata exists if expected

## Table Styling Gotchas

- `copyPaste` with `PASTE_FORMAT` can copy colors and some banding, but it may not recreate a real Google Sheets `tables` object.
- A sheet can look close visually while still missing `tables`; missing `tables` means the UI may not show the table name chip or header dropdown controls.
- `tables` and `bandedRanges` are related but not identical. Verify both when matching a source tab that uses the modern Google Sheets table UI.
- Table names must be unique within a spreadsheet. If the source table is named `Table1`, use a target-specific name such as `SingleSession`.
- `clear()` can remove assumptions about formatting and structure. Reapply table metadata and dimensions after writing values.
- Expanding a table can leave blank rows inside the table range. If a later script reads those rows and rewrites `A1:...`, it can accidentally make the blanks permanent. Filter/validate by the key column before rewriting.

## Append Guard Pattern

Use this pattern before appending to an existing table-backed sheet:

```python
values = worksheet.get_all_values()
headers = values[0]
existing_rows = [row for row in values[1:] if row and row[0].strip()]

if len(existing_rows) < expected_min_rows:
    raise RuntimeError("Refuse to overwrite: key identifier rows are unexpectedly missing")

append_start = len(values) + 1
worksheet.update(
    values=append_rows,
    range_name=f"A{append_start}:H{append_start + len(append_rows) - 1}",
    value_input_option="RAW",
)
```

After appending values, update only table/banding metadata ranges to include the new rows. Do not rewrite the existing value range unless the task is explicitly a full rebuild and the identifier-row count check passes.

## Minimal Metadata Read

```python
import gspread

client = gspread.oauth(scopes=["https://www.googleapis.com/auth/spreadsheets"])
spreadsheet_id = "..."
url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
params = {
    "includeGridData": "false",
    "fields": "sheets(properties(sheetId,title),basicFilter,filterViews,bandedRanges,tables)",
}
metadata = client.http_client.request("get", url, params=params).json()
```

## Worksheet By Gid

```python
def worksheet_by_gid(spreadsheet, gid: int):
    for worksheet in spreadsheet.worksheets():
        if worksheet.id == gid:
            return worksheet
    raise RuntimeError(f"Worksheet gid={gid} not found")
```

## Completion Evidence

Report concise evidence:

- target spreadsheet and tab
- data rows written
- header verification
- key identifiers written
- whether `tables` and `bandedRanges` are present
- any fallback or data-source caveat
