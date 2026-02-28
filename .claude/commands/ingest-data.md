Trigger data ingestion from the landing zone to the encrypted data lake.

## Steps

1. Scan `data/raw/` for new files
2. Determine data type from file extension and content structure
3. Parse and validate structure (JSON, CSV, XML, plain text)
4. Encrypt each record with `age` using the configured recipient key
5. Store in `data/lake/` with structured naming: `{category}/{date}/{hash}.age`
6. Write audit entry to `data/audit/ingest.jsonl`
7. Delete processed files from `data/raw/`
8. Report: files processed, records ingested, any errors

## Validation

After ingestion, verify:
- `data/raw/` is empty (all files processed or errors logged)
- `data/lake/` has new encrypted files
- `data/audit/ingest.jsonl` has entries for this run
- Run `uv run pytest tests/test_data_mcp.py -v` to verify MCP can query the ingested data
