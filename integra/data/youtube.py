"""YouTube transcript and metadata extraction for KB ingestion.

Extracts video metadata (title, chapters, tags) and auto-generated
transcripts via yt-dlp (run through uvx — no install required).
Output: structured markdown grouped by chapter for KB consumption.

Architecture: data/ module (extraction + transform), not integrations/
(no external service auth needed — yt-dlp handles YouTube directly).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class Chapter:
    """A video chapter with start time and title."""

    start_ms: int
    title: str

    @property
    def timestamp(self) -> str:
        """Format as [MM:SS]."""
        total_sec = self.start_ms // 1000
        m, s = divmod(total_sec, 60)
        return f"[{m:02d}:{s:02d}]"


@dataclass
class TranscriptSegment:
    """A single transcript segment with timing."""

    start_ms: int
    text: str

    @property
    def timestamp(self) -> str:
        """Format as [MM:SS]."""
        total_sec = self.start_ms // 1000
        m, s = divmod(total_sec, 60)
        return f"[{m:02d}:{s:02d}]"


@dataclass
class VideoExtract:
    """Complete extraction result from a YouTube video."""

    video_id: str
    title: str
    channel: str
    upload_date: str
    duration_sec: int
    view_count: int
    description: str
    tags: list[str] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    segments: list[TranscriptSegment] = field(default_factory=list)
    url: str = ""

    @property
    def duration_fmt(self) -> str:
        """Format duration as XmYs."""
        m, s = divmod(self.duration_sec, 60)
        return f"{m}m{s}s"


_ALLOWED_YOUTUBE_DOMAINS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}


def _validate_youtube_url(url: str) -> None:
    """Validate that a URL points to YouTube. Rejects file://, other schemes, other domains."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        msg = f"Invalid URL scheme '{parsed.scheme}' — only http/https allowed"
        raise ValueError(msg)
    if parsed.hostname not in _ALLOWED_YOUTUBE_DOMAINS:
        msg = f"Invalid domain '{parsed.hostname}' — only YouTube URLs allowed"
        raise ValueError(msg)


def extract_metadata(url: str) -> VideoExtract:
    """Extract video metadata via yt-dlp --dump-json."""
    _validate_youtube_url(url)
    result = subprocess.run(
        ["uvx", "yt-dlp", "--dump-json", "--skip-download", url],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    d = json.loads(result.stdout)

    chapters = [Chapter(start_ms=int(ch["start_time"] * 1000), title=ch["title"]) for ch in d.get("chapters", [])]

    return VideoExtract(
        video_id=d["id"],
        title=d["title"],
        channel=d["channel"],
        upload_date=d.get("upload_date", ""),
        duration_sec=d.get("duration", 0),
        view_count=d.get("view_count", 0),
        description=d.get("description", ""),
        tags=d.get("tags", []),
        chapters=chapters,
        url=url,
    )


def extract_transcript(url: str, lang: str = "en") -> list[TranscriptSegment]:
    """Extract auto-generated transcript via yt-dlp."""
    _validate_youtube_url(url)
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "transcript"
        subprocess.run(
            [
                "uvx",
                "yt-dlp",
                "--write-auto-sub",
                "--skip-download",
                "--sub-lang",
                lang,
                "--sub-format",
                "json3",
                "-o",
                str(out_path),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )

        json_file = Path(f"{out_path}.{lang}.json3")
        if not json_file.exists():
            return []

        data = json.loads(json_file.read_text())

    segments: list[TranscriptSegment] = []
    for event in data.get("events", []):
        if "segs" in event:
            text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
            if text:
                segments.append(
                    TranscriptSegment(
                        start_ms=event.get("tStartMs", 0),
                        text=text,
                    )
                )
    return segments


def extract_video(url: str, lang: str = "en") -> VideoExtract:
    """Full extraction: metadata + transcript in one call."""
    video = extract_metadata(url)
    video.segments = extract_transcript(url, lang=lang)
    return video


def render_kb_markdown(video: VideoExtract) -> str:
    """Render a VideoExtract into chaptered KB markdown."""
    lines: list[str] = []
    today = date.today().isoformat()

    # Header
    lines.append(f"# KB Extract: {video.title}")
    lines.append("")
    lines.append(f"> Source: {video.url}")
    lines.append(f"> Channel: {video.channel} | Upload: {video.upload_date} | Duration: {video.duration_fmt}")
    lines.append(f"> Extracted: {today} via yt-dlp + integra youtube-extract")
    if video.tags:
        lines.append(f"> Tags: {', '.join(video.tags[:15])}")
    lines.append("")

    # Metadata table
    lines.append("## Metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Video ID | `{video.video_id}` |")
    lines.append(f"| Channel | {video.channel} |")
    lines.append(f"| Upload | {video.upload_date} |")
    lines.append(f"| Duration | {video.duration_fmt} |")
    lines.append(f"| Views | {video.view_count} |")
    lines.append("")

    # Description
    if video.description:
        lines.append("## Description")
        lines.append("")
        lines.append(video.description[:1000])
        lines.append("")

    lines.append("---")
    lines.append("")

    # Chapters + transcript
    if video.chapters:
        for i, chapter in enumerate(video.chapters):
            ch_end = video.chapters[i + 1].start_ms if i + 1 < len(video.chapters) else video.duration_sec * 1000
            ch_segs = [s for s in video.segments if chapter.start_ms <= s.start_ms < ch_end]

            lines.append(f"## {chapter.timestamp} {chapter.title}")
            lines.append("")

            # Group segments into paragraphs (~5 segments each)
            para: list[str] = []
            for seg in ch_segs:
                para.append(seg.text)
                if len(para) >= 5:
                    lines.append(" ".join(para))
                    lines.append("")
                    para = []
            if para:
                lines.append(" ".join(para))
                lines.append("")
    else:
        # No chapters — single section
        lines.append("## Full Transcript")
        lines.append("")
        para_full: list[str] = []
        for seg in video.segments:
            para_full.append(seg.text)
            if len(para_full) >= 5:
                lines.append(" ".join(para_full))
                lines.append("")
                para_full = []
        if para_full:
            lines.append(" ".join(para_full))
            lines.append("")

    # Placeholder sections for agent to fill
    lines.append("---")
    lines.append("")
    lines.append("## Key Takeaways")
    lines.append("")
    lines.append("<!-- Agent fills: 3-5 bullet points -->")
    lines.append("")
    lines.append("## Relevance to integra")
    lines.append("")
    lines.append("<!-- Agent fills: how content relates to integra -->")
    lines.append("")

    return "\n".join(lines)
