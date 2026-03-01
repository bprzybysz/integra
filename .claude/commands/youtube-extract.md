Extract knowledge base content from a YouTube video.

## Usage

```
/youtube-extract <URL> [--output PATH]
```

Default output: `tmp/yt/<video-id>.md`

## Steps

1. Extract video metadata via `uvx yt-dlp --dump-json --skip-download "<URL>"`
   - Title, channel, upload date, duration, views, description, tags
   - Chapters (timestamps + titles) — if available
2. Extract transcript via `uvx yt-dlp --write-auto-sub --skip-download --sub-lang en --sub-format json3 -o "/tmp/yt-transcript" "<URL>"`
3. Parse transcript JSON: group segments into paragraphs, align to chapters
4. Generate KB extract markdown using the template structure below
5. Save to output path
6. Report: title, duration, chapter count, segment count, output path

## Template Structure

```markdown
# KB Extract: {title}

> Source: {url}
> Channel: {channel} | Upload: {date} | Duration: {duration}
> Extracted: {today} via yt-dlp + integra youtube-extract
> Tags: {tags}

---

## Metadata

| Field | Value |
|-------|-------|
| Video ID | {id} |
| Channel | {channel} |
| Upload | {date} |
| Duration | {duration} |
| Views | {views} |

## Description

{description}

---

## Chapters

| Time | Title |
|------|-------|
| [MM:SS] | {chapter_title} |

---

## [MM:SS] {chapter_title}

{transcript paragraphs grouped by chapter}

---

## Key Takeaways

{agent fills: 3-5 bullet points summarizing actionable insights}

## Relevance to integra

{agent fills: how content relates to integra roadmap/architecture}
```

## Validation

- Output file exists and has content
- All chapters from metadata appear as sections
- Transcript covers full video duration (last segment within 30s of video end)
- No empty chapter sections

## Notes

- `yt-dlp` runs via `uvx` — no install needed
- Auto-generated captions (ASR) are used when manual captions unavailable
- For videos without chapters, use single "Full Transcript" section
- Sensitive content (drug references, personal data) stays in tmp/ (gitignored)
