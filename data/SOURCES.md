# Managing calendar sources

The private source of truth is `data/sources.xlsx`. Both this workbook and its
generated `data/sources.csv` are intentionally ignored by Git and must never be
force-added. The worksheet must be named `Sources` and contain these columns
in this exact order:

```text
source_id, source, sport, competition, enabled, source_type
```

Use one row per calendar source. `source_id` must be unique and should not be
changed after a source is created. `enabled` accepts `true` or `false`.
Supported `source_type` values are `ics`, `wpbl_api`, and `wsl_official`.

After editing the workbook, generate the application CSV with:

```bash
python export_sources.py
```

The exporter validates required fields, duplicate IDs, boolean values, and
source types before replacing `data/sources.csv`. If validation fails, the
existing CSV remains unchanged.

For scheduled GitHub Actions runs, store the generated CSV in the encrypted
repository secret `SOURCES_CSV_BASE64`. On macOS, copy its Base64 representation
to the clipboard with:

```bash
base64 < data/sources.csv | pbcopy
```

In the GitHub repository, open **Settings → Secrets and variables → Actions →
New repository secret**, name it `SOURCES_CSV_BASE64`, and paste the clipboard
contents. The workflow reconstructs the private CSV only inside the temporary
Actions runner. It is not committed or copied into the website.

Generated `data/events.csv` remains public because the website is built from
it, but the automation blanks its internal `source_url` field before saving.
Public event-detail URLs remain available so visitors can open official match
pages.
