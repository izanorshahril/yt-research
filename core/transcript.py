import logging
import ssl
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


def get_unverified_session() -> requests.Session:
    session = requests.Session()
    session.verify = False
    return session


def format_timestamp(seconds: float) -> str:
    """Formats floating seconds to HH:MM:SS or MM:SS."""
    seconds_int = int(seconds)
    m, s = divmod(seconds_int, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fetch_transcript(video_id: str, languages: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Fetches timestamped transcript for a YouTube video ID.
    Returns structured transcript dict with segments [{start, duration, start_formatted, text}].
    """
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

            full_text = " ".join(full_text_parts)
            result.update({
                "has_transcript": len(segments) > 0,
                "segments": segments,
                "full_text": full_text,
                "word_count": len(full_text.split()),
                "error": None if len(segments) > 0 else "Transcript empty"
            })
            return result

    except Exception as e:
        logger.warning(f"youtube-transcript-api failed for {video_id}: {e}")
        result["error"] = str(e)

    # Method 2: yt-dlp fallback
    try:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en.*", "en"],
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            info = ydl.extract_info(video_url, download=False)
            if info:
                subs = info.get("subtitles") or info.get("automatic_captions") or {}
                if subs:
                    result["has_transcript"] = True
                    result["error"] = None
                    result["language"] = "en"
                    result["full_text"] = info.get("description") or "Transcript metadata extracted via yt-dlp"
                    return result
    except Exception as fallback_err:
        logger.error(f"yt-dlp fallback failed for {video_id}: {fallback_err}")

    return result
