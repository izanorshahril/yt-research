import logging
import re
import ssl
import time
import urllib3
import requests
from typing import List, Dict, Any, Optional
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import yt_dlp

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

logger = logging.getLogger(__name__)


def extract_video_id(url_or_id: str) -> str:
    """Extracts YouTube video ID from a URL or returns the ID as-is."""
    url_or_id = url_or_id.strip()
    match = re.search(r"(?:v=|\/|be\/|embed\/)([a-zA-Z0-9_-]{11})", url_or_id)
    if match:
        return match.group(1)
    return url_or_id


def get_unverified_session() -> requests.Session:
    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def format_timestamp(seconds: float) -> str:
    """Formats floating seconds to HH:MM:SS or MM:SS."""
    seconds_int = int(seconds)
    m, s = divmod(seconds_int, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_vtt_content(vtt_text: str) -> List[Dict[str, Any]]:
    """Parses simple WebVTT content into transcript segments."""
    segments = []
    lines = vtt_text.splitlines()
    i = 0
    time_pattern = re.compile(r"(\d{2}:)?\d{2}:\d{2}\.\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}\.\d{3}")
    
    while i < len(lines):
        line = lines[i].strip()
        if time_pattern.search(line):
            times = line.split("-->")
            start_str = times[0].strip()
            # Convert timestamp to seconds
            parts = start_str.split(":")
            if len(parts) == 3:
                s = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                s = float(parts[0]) * 60 + float(parts[1])
            else:
                s = 0.0
                
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip() and not time_pattern.search(lines[i]):
                clean = re.sub(r"<[^>]+>", "", lines[i].strip())
                if clean and clean not in text_lines:
                    text_lines.append(clean)
                i += 1
            if text_lines:
                clean_text = " ".join(text_lines)
                segments.append({
                    "start": s,
                    "duration": 0.0,
                    "start_formatted": format_timestamp(s),
                    "text": clean_text
                })
        else:
            i += 1
    return segments


def fetch_transcript(
    url_or_id: str,
    languages: Optional[List[str]] = None,
    cookies_from_browser: Optional[str] = None,
    delay: float = 0.0
) -> Dict[str, Any]:
    """
    Fetches timestamped transcript for a YouTube video ID or URL.
    Returns structured transcript dict with segments [{start, duration, start_formatted, text}].
    """
    if delay > 0:
        time.sleep(delay)

    video_id = extract_video_id(url_or_id)
    if not languages:
        languages = ["en", "en-US", "en-GB", "a.en"]

    result = {
        "video_id": video_id,
        "has_transcript": False,
        "language": "en",
        "is_generated": False,
        "segments": [],
        "full_text": "",
        "word_count": 0,
        "error": None
    }

    # Method 1: youtube-transcript-api with unverified session
    try:
        session = get_unverified_session()
        api = YouTubeTranscriptApi(http_client=session)

        transcript_obj = None
        try:
            transcript_list = api.list(video_id)
            try:
                transcript_obj = transcript_list.find_transcript(languages)
            except Exception:
                try:
                    transcript_obj = transcript_list.find_generated_transcript(languages)
                except Exception:
                    for t in transcript_list:
                        transcript_obj = t
                        break
        except Exception:
            pass

        raw_snippets = None
        if transcript_obj:
            raw_snippets = transcript_obj.fetch()
            result["language"] = getattr(transcript_obj, "language_code", "en")
            result["is_generated"] = getattr(transcript_obj, "is_generated", False)
        else:
            try:
                raw_snippets = api.fetch(video_id, languages=languages)
            except Exception:
                try:
                    raw_snippets = api.fetch(video_id)
                except Exception:
                    pass

        if raw_snippets:
            segments = []
            full_text_parts = []

            for item in raw_snippets:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    start = item.get("start", 0.0)
                    duration = item.get("duration", 0.0)
                else:
                    text = getattr(item, "text", "")
                    start = getattr(item, "start", 0.0)
                    duration = getattr(item, "duration", 0.0)

                clean_text = text.replace("\n", " ").strip()
                if clean_text:
                    segments.append({
                        "start": float(start),
                        "duration": float(duration),
                        "start_formatted": format_timestamp(float(start)),
                        "text": clean_text
                    })
                    full_text_parts.append(clean_text)

            if segments:
                full_text = " ".join(full_text_parts)
                result.update({
                    "has_transcript": True,
                    "segments": segments,
                    "full_text": full_text,
                    "word_count": len(full_text.split()),
                    "error": None
                })
                return result

    except Exception as e:
        logger.warning(f"youtube-transcript-api failed for {video_id}: {e}")
        result["error"] = str(e)

    # Method 2: yt-dlp fallback with direct subtitle track parsing (json3 / vtt)
    try:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en.*", "en", "a.en"],
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "extractor_args": {"youtube": {"player_client": ["android", "mweb", "web", "ios"]}}
        }
        if cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info:
                subs = info.get("subtitles") or info.get("automatic_captions") or {}
                en_keys = [k for k in subs if k.startswith("en") or k == "a.en"]
                if not en_keys:
                    en_keys = list(subs.keys())

                if en_keys:
                    en_key = en_keys[0]
                    formats = subs[en_key]
                    target_fmt = next((f for f in formats if f.get("ext") == "json3"), None) or \
                                 next((f for f in formats if f.get("ext") == "vtt"), None) or \
                                 formats[0]

                    sub_url = target_fmt.get("url")
                    if sub_url:
                        session = get_unverified_session()
                        resp = session.get(sub_url, timeout=12)
                        segments = []
                        full_text_parts = []

                        if target_fmt.get("ext") == "json3":
                            sub_data = resp.json()
                            events = sub_data.get("events", [])
                            for ev in events:
                                segs = ev.get("segs", [])
                                raw = "".join(s.get("utf8", "") for s in segs).strip()
                                clean_text = raw.replace("\n", " ").strip()
                                if clean_text:
                                    start_s = ev.get("tStartMs", 0) / 1000.0
                                    dur_s = ev.get("dDurationMs", 0) / 1000.0
                                    segments.append({
                                        "start": float(start_s),
                                        "duration": float(dur_s),
                                        "start_formatted": format_timestamp(float(start_s)),
                                        "text": clean_text
                                    })
                                    full_text_parts.append(clean_text)
                        else:
                            segments = parse_vtt_content(resp.text)
                            full_text_parts = [s["text"] for s in segments]

                        if segments:
                            full_text = " ".join(full_text_parts)
                            result.update({
                                "has_transcript": True,
                                "language": en_key,
                                "segments": segments,
                                "full_text": full_text,
                                "word_count": len(full_text.split()),
                                "error": None
                            })
                            return result

    except Exception as fallback_err:
        logger.error(f"yt-dlp fallback failed for {video_id}: {fallback_err}")
        result["error"] = str(fallback_err)

    return result
