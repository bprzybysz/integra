"""Tests for integra.data.youtube — YouTube transcript extraction."""

from __future__ import annotations

import json
from unittest.mock import patch

from integra.data.youtube import (
    Chapter,
    TranscriptSegment,
    VideoExtract,
    extract_metadata,
    extract_transcript,
    render_kb_markdown,
)

# --- Unit tests (no network) ---


class TestChapter:
    def test_timestamp_zero(self) -> None:
        ch = Chapter(start_ms=0, title="Intro")
        assert ch.timestamp == "[00:00]"

    def test_timestamp_minutes(self) -> None:
        ch = Chapter(start_ms=125000, title="Ch2")
        assert ch.timestamp == "[02:05]"


class TestTranscriptSegment:
    def test_timestamp(self) -> None:
        seg = TranscriptSegment(start_ms=62000, text="hello")
        assert seg.timestamp == "[01:02]"


class TestVideoExtract:
    def test_duration_fmt(self) -> None:
        v = VideoExtract(
            video_id="abc",
            title="Test",
            channel="Ch",
            upload_date="20260101",
            duration_sec=125,
            view_count=0,
            description="",
        )
        assert v.duration_fmt == "2m5s"


class TestRenderKbMarkdown:
    def _make_video(self) -> VideoExtract:
        return VideoExtract(
            video_id="test123",
            title="Test Video",
            channel="Test Channel",
            upload_date="20260301",
            duration_sec=120,
            view_count=500,
            description="A test video.",
            tags=["ai", "coding"],
            url="https://www.youtube.com/watch?v=test123",
            chapters=[
                Chapter(start_ms=0, title="Intro"),
                Chapter(start_ms=60000, title="Main"),
            ],
            segments=[
                TranscriptSegment(start_ms=0, text="Hello world."),
                TranscriptSegment(start_ms=5000, text="Welcome."),
                TranscriptSegment(start_ms=60000, text="Main content."),
                TranscriptSegment(start_ms=65000, text="More content."),
            ],
        )

    def test_header_present(self) -> None:
        md = render_kb_markdown(self._make_video())
        assert "# KB Extract: Test Video" in md

    def test_source_url(self) -> None:
        md = render_kb_markdown(self._make_video())
        assert "https://www.youtube.com/watch?v=test123" in md

    def test_chapters_as_sections(self) -> None:
        md = render_kb_markdown(self._make_video())
        assert "## [00:00] Intro" in md
        assert "## [01:00] Main" in md

    def test_segments_in_chapters(self) -> None:
        md = render_kb_markdown(self._make_video())
        assert "Hello world." in md
        assert "Main content." in md

    def test_no_chapters_fallback(self) -> None:
        v = self._make_video()
        v.chapters = []
        md = render_kb_markdown(v)
        assert "## Full Transcript" in md
        assert "Hello world." in md

    def test_tags_in_header(self) -> None:
        md = render_kb_markdown(self._make_video())
        assert "ai, coding" in md

    def test_metadata_table(self) -> None:
        md = render_kb_markdown(self._make_video())
        assert "| Video ID | `test123` |" in md

    def test_takeaway_placeholder(self) -> None:
        md = render_kb_markdown(self._make_video())
        assert "## Key Takeaways" in md
        assert "## Relevance to integra" in md


class TestExtractMetadata:
    def test_parses_yt_dlp_json(self) -> None:
        fake_json = json.dumps(
            {
                "id": "abc123",
                "title": "Test",
                "channel": "Ch",
                "upload_date": "20260101",
                "duration": 300,
                "view_count": 1000,
                "description": "Desc",
                "tags": ["t1"],
                "chapters": [
                    {"start_time": 0, "title": "Intro", "end_time": 60},
                    {"start_time": 60, "title": "Body", "end_time": 300},
                ],
            }
        )
        with patch("integra.data.youtube.subprocess.run") as mock_run:
            mock_run.return_value.stdout = fake_json
            v = extract_metadata("https://youtube.com/watch?v=abc123")

        assert v.video_id == "abc123"
        assert v.title == "Test"
        assert len(v.chapters) == 2
        assert v.chapters[1].start_ms == 60000

    def test_no_chapters(self) -> None:
        fake_json = json.dumps(
            {
                "id": "x",
                "title": "T",
                "channel": "C",
                "upload_date": "",
                "duration": 60,
                "view_count": 0,
                "description": "",
                "tags": [],
            }
        )
        with patch("integra.data.youtube.subprocess.run") as mock_run:
            mock_run.return_value.stdout = fake_json
            v = extract_metadata("https://youtube.com/watch?v=x")

        assert v.chapters == []


class TestExtractTranscript:
    def test_parses_json3_format(self, tmp_path: object) -> None:
        fake_json3 = json.dumps(
            {
                "events": [
                    {
                        "tStartMs": 0,
                        "segs": [{"utf8": "Hello "}, {"utf8": "world"}],
                    },
                    {
                        "tStartMs": 5000,
                        "segs": [{"utf8": "Next line"}],
                    },
                    {
                        "tStartMs": 10000,
                        "segs": [{"utf8": "\n"}],
                    },
                ]
            }
        )

        def fake_run(*args: object, **kwargs: object) -> object:
            # Write the fake json3 file where extract_transcript expects it
            import types

            cmd = args[0]
            assert isinstance(cmd, list)
            out_template = cmd[-2]  # -o argument
            json_path = f"{out_template}.en.json3"
            from pathlib import Path

            Path(json_path).write_text(fake_json3)
            return types.SimpleNamespace(stdout="", stderr="", returncode=0)

        with patch("integra.data.youtube.subprocess.run", side_effect=fake_run):
            segs = extract_transcript("https://youtube.com/watch?v=x")

        assert len(segs) == 2  # empty "\n" segment filtered
        assert segs[0].text == "Hello world"
        assert segs[0].start_ms == 0
        assert segs[1].text == "Next line"
