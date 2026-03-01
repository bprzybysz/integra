# /prp-sync — PRP ↔ GH Bidirectional Sync Audit

Audit synchronization between `.claude/PRPs/plans/` and GitHub issues.

## Steps

1. **Find all PRPs**: `Glob(".claude/PRPs/plans/prp-*.md")` — extract issue numbers from filenames using regex `prp-(\d+)`

2. **Check GH state for each**: For each unique issue number N found:
   ```bash
   gh issue view <N> --json number,state,title
   ```

3. **Report mismatches**:
   - Active PRP (not archived) + closed GH issue → warn: "PRP exists but issue #N is closed"
   - GH issue open but no PRP in `.claude/PRPs/plans/prp-<NNN>-*` → info only (not all issues need PRPs)

4. **Summary output**:
   ```
   PRP Sync Report — <date>
   PRPs found: N
   Mismatches: M

   Issues requiring attention:
   - prp-049-*.md: issue #49 is CLOSED (archive or reopen?)
   ```

## Notes

- This is a read-only audit — no files are modified
- Run after `/prp-ralph` completes if unsure about sync state
- Not required for normal workflow — CLAUDE.md rules handle automatic sync
- If no PRPs found, report: "No PRPs found in .claude/PRPs/plans/"
