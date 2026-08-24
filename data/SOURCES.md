# Managing calendar sources

The private source of truth is `data/sources.xlsx`. Both this workbook and its
generated `data/sources.csv` are intentionally ignored by Git and must never be
force-added. The worksheet should be named `Sources` and must contain these
columns (their order does not matter):

```text
source_id, source, sport, competition, enabled, source_type, country
```

Additional workbook columns are allowed for planning or management and are
ignored by the exporter. The generated CSV contains only the seven columns
listed above.

Use one row per calendar source. `source_id` must be unique and should not be
changed after a source is created. `enabled` accepts `true` or `false`.
`source_type` is exported as entered and is not validated by the exporter.
The event collector must support a source type before a row using it can be
enabled successfully.

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
