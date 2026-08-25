---
name: google-sheets-editor
description: Update existing Google Sheets tabs from local data, database query results, or generated rows while preserving sheet structure, gid targeting, table metadata, banding, filters, dimensions, verification evidence, and Drive file smart chips. Use when writing to a Google Sheet, copying the format of another tab, fixing Sheets styling that depends on real tables rather than plain cell formatting, or converting Drive URLs into file-name/icon chips.
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
- Before writing Drive file smart chips, inspect OAuth scopes without printing credentials. The Sheets API requires `drive.file`, `drive.readonly`, or `drive` in addition to spreadsheet access.
- Never silently widen OAuth scopes or trigger a new consent grant. If the existing token lacks a Drive scope, use the authenticated Google Sheets UI through the `ego-browser` skill after obtaining browser control.
- Before bulk URL-to-chip conversion, back up the exact target range and verify the identifier-to-URL mapping. A successful conversion must change only the requested cell values/chip runs, not surrounding data or formatting.

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

## Drive File Smart Chips

Use this workflow when the user wants a Drive file icon and filename such as `report-01.pdf` instead of a visible long URL or `HYPERLINK()` label.

### API Contract and Scope Gate

Google Sheets represents a writable Drive file chip with `CellData.chipRuns[].chip.richLinkProperties.uri`. The write representation uses one `@` placeholder in `userEnteredValue`:

```json
{
  "userEnteredValue": {"stringValue": "@"},
  "chipRuns": [
    {
      "startIndex": 0,
      "chip": {
        "richLinkProperties": {
          "uri": "https://drive.google.com/file/d/<file_id>/view"
        }
      }
    }
  ]
}
```

Write only `userEnteredValue,chipRuns` through `updateCells`; omitting `userEnteredFormat` preserves existing colors, borders, alignment, and dimensions. `mimeType` is output-only. Only Drive files are writable as rich-link chips, and each URI must be at most 2,000 bytes.

Before an API write, inspect `~/.config/gspread/authorized_user.json` and report booleans/counts only—never the token or refresh credentials:

```python
import json
from pathlib import Path

token = json.loads((Path.home() / ".config/gspread/authorized_user.json").read_text())
scopes = set(token.get("scopes", []))
has_drive_scope = bool(
    scopes
    & {
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive",
    }
)
```

Writing file chips requires `has_drive_scope`. Spreadsheet-only OAuth is sufficient to read and verify `chipRuns`, but not to create them through the API.

Official schema: `https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#ChipRun`.

### Spreadsheet-Only OAuth Fallback

When the token lacks a Drive scope, do not reauthorize silently and do not degrade to fake filename links. Read and follow the `ego-browser` skill, then use the already authenticated Sheets UI:

1. If the user controls the task space, stop and request an explicit handoff. Do not route around that control state with another browser or API mutation.
2. Back up the requested range and record a digest of the reference sheet plus target content/format outside the range.
3. Convert one URL as a probe: select the cell, then choose `Insert → Smart chips → Convert to file chip`.
4. Read the probe back through Sheets API and require its rich-link URI to equal the expected Drive URL.
5. Select only the remaining requested range(s) and run the same conversion in bounded batches.
6. Read back every cell, visually inspect the actual sheet, and return browser control without closing pages when the user asked to review them.

### Smart-Chip Verification

Do not identify a chip from `formattedValue` alone. UI conversion commonly changes `userEnteredValue` and `formattedValue` from the URL to the Drive filename.

When reading, `chipRuns` includes both chipped and non-chipped runs. Count only runs where `chip.richLinkProperties.uri` exists; do not require `len(chipRuns) == 1`.

For every converted cell, verify:

- exactly one rich-link URI and exact agreement with the source/report/profile mapping
- expected filename for the report ordinal
- output `mimeType` such as `application/pdf`
- unique URI count equals expected file count
- zero raw Drive URLs remain in the converted range
- reference-sheet digest and target static-content/format digest remain unchanged
- a screenshot shows chips in the intended rows and columns

Preserve a local pre-write backup and a post-write receipt containing range, counts, mapping checksum, before/after digests, and verification totals. Do not store OAuth material in either artifact.

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
- for Drive smart chips: converted range, chip count, unique rich-link count, MIME-type count, raw URLs remaining, and before/after source/static digests
- whether browser control was handed back and requested review pages were kept open
