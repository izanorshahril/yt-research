from typing import Dict, Any


def format_srt_timestamp(seconds: float) -> str:
    """Formats seconds to SRT format: HH:MM:SS,mmm"""
    sec = int(seconds)
    millis = int((seconds - sec) * 1000)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def to_markdown(video: Dict[str, Any], transcript: Dict[str, Any]) -> str:
    """Generates clean Markdown representation of video and timestamped transcript."""
    title = video.get("title", "Untitled Video")
    video_id = video.get("video_id", "")
    upload_date = video.get("upload_date", "Unknown Date")
    url = video.get("url", f"https://www.youtube.com/watch?v={video_id}")
    duration = video.get("duration_str", "Unknown")
    word_count = transcript.get("word_count", 0)
    segments = transcript.get("segments", [])

    lines = [
        f"# {title}",
        "",
        f"- **Channel**: {video.get('channel_handle', 'N/A')}",
        f"- **Upload Date**: {upload_date}",
        f"- **Duration**: {duration}",
        f"- **Word Count**: {word_count}",
        f"- **Video Link**: [{url}]({url})",
        "",
        "## Transcript with Timestamps",
        ""
    ]

    if not segments:
        lines.append("*No transcript segments available for this video.*")
    else:
        for seg in segments:
            start_str = seg.get("start_formatted", "00:00")
            start_sec = int(seg.get("start", 0))
            text = seg.get("text", "")
            jump_url = f"https://youtu.be/{video_id}?t={start_sec}"
            lines.append(f"- [[{start_str}]({jump_url})] {text}")

    return "\n".join(lines)


def to_srt(transcript: Dict[str, Any]) -> str:
    """Generates SRT (SubRip Subtitle) format."""
    segments = transcript.get("segments", [])
    if not segments:
        return ""

    srt_items = []
    for idx, seg in enumerate(segments, 1):
        start_sec = seg.get("start", 0.0)
        dur_sec = seg.get("duration", 2.0)
        end_sec = start_sec + dur_sec
        start_fmt = format_srt_timestamp(start_sec)
        end_fmt = format_srt_timestamp(end_sec)
        text = seg.get("text", "")

        srt_items.append(f"{idx}\n{start_fmt} --> {end_fmt}\n{text}\n")

    return "\n".join(srt_items)


def to_txt(video: Dict[str, Any], transcript: Dict[str, Any]) -> str:
    """Generates plain text transcript with timestamps."""
    title = video.get("title", "Untitled Video")
    upload_date = video.get("upload_date", "")
    segments = transcript.get("segments", [])

    header = f"{title} ({upload_date})\nURL: {video.get('url', '')}\n" + "=" * 50 + "\n\n"
    if not segments:
        return header + "No transcript available."

    lines = [header]
    for seg in segments:
        start_fmt = seg.get("start_formatted", "00:00")
        lines.append(f"[{start_fmt}] {seg.get('text', '')}")

    return "\n".join(lines)
